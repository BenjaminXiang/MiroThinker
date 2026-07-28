# Verification: rebuild-canonical-v2-knowledge-platform

## Current status

S12A and exactly Task `12.1` are Accepted on fresh r12 evidence at `2026-07-23`. The 2026-07-26
user-confirmed lean E2E rebaseline retires Tasks `2.8`, `8.1`, `8.8`, and `9.8` as separate gates.
The current ledger is `76/80`; the four open tasks are exactly `12.3`-`12.6`.

Tasks 5.1-5.7, the corrected aggregate S5 surface, and Tasks 6.1-6.8/Aggregate S6 are Accepted. On 2026-07-13 ADR-012 introduced
the narrow Task 5.7/S5G precision-preserving temporal correction after a real S6c interface failure;
the user selected `explicit-calendar-v1`, and S5G was Accepted at `2026-07-13T09:19:45Z` after its
pure, real-disposable PostgreSQL, static, strict OpenSpec, scope, and review gates passed. Tasks 6.1
(PRD domain/relationship catalog), 6.2 (domain-inclusion RED), 6.3 (typed domain projection), 6.4
(relationship RED), 6.5 (relationship projection/persistence), 6.6 (path-eligibility RED), 6.7
(path-eligibility GREEN), and 6.8 (aggregate bounded-candidate review) are Accepted. OpenSpec reports
71/80 tasks complete on the V2 integration line. ADR-013 through ADR-022 add S2C/tasks
2.7-2.8 and the now-Accepted S6R/tasks 6.9-6.11 without rewriting the historical S2/S6 acceptance.
S6R1-S6R5, S7A/Task 7.1 release-lifecycle RED, S7B/Task 7.2 KnowledgeBuild, S7C/Task 7.3 typed
candidate projection, S7D/Task 7.4 index RED, S7E/Task 7.5 isolated index construction, and
S7F/Task 7.6 deterministic reconciliation/release publication, S7G/Task 7.7 RED, and S7H/Task 7.7
isolated DB/index parity and rollback rehearsal are Accepted; aggregate S7 and its S7I lookup-
eligibility lineage correction are Accepted. S8L1's release-bundle-bound physical exact lookup and
S8L2's displayed-set structured lookup are Accepted as Task 8.3 predecessors without checking Task
8.3. S8P1's release-bound query planner and S8P2's finite proposal taxonomy/safety, material-part,
and assessment-intent completion are Accepted; Task 8.2 is closed. S8E1's release-bound
exact/structured plus current-Web composition root is Accepted as a Task 8.3 predecessor without
checking Task 8.3. S8L3's release-scoped lexical phrase adapter is also Accepted as a Task 8.3
predecessor without checking Task 8.3. S7J's vector eligibility-lineage and full-point inventory-
hash correction is Accepted without changing historical S7 task status or Task 8.3. S8V1's audited
release-scoped vector adapter and release-authority trace seam are Accepted as another Task 8.3
predecessor without checking Task 8.3. S8V2's finite Professor identity/research/both selector,
audited lookup-derived display authority, and release-bound view/name validation are also Accepted
at the unchanged ledger without checking Task 8.3. S8IR1's release-scoped internal Person filter
and Technology definition lookup is also Accepted at the unchanged ledger: it replays S7 internal
authority, retains public-origin identity/display, and leaves relationship state to the still-open
relationship path. S7K's release-scoped relationship-publication authority correction is now
Accepted at the same ledger: exact S6 relationship replay, seven projection manifests, the
relationship section, complete build-manifest hash, and fresh effect-before-validation bundles are
bound without changing historical S7 task status. S8R1's release-scoped Technology-to-Company
relationship traversal is also Accepted at the unchanged ledger: it executes the three exact
Product-to-Technology states from the S7K authority, keeps claims Product-scoped and Company identity
locator-only, and performs no physical relationship reopen. S8R2's displayed Company-to-Patent
applicant traversal is also Accepted at the unchanged ledger: it reverse-traverses only exact
current `patent_has_applicant` authority, returns Patent-scoped results with complete lineage, and
keeps the displayed Company source-side only. S8R3's displayed Professor-to-Paper attribution
traversal is now also Accepted at the unchanged ledger: it follows only exact accepted current
`professor_attributed_to_paper` authority, returns Paper, keeps Professor source-side only, and
rejects relationship path/lane drift before Web effects. S8R4's displayed Paper-to-Professor
inverse traversal is also Accepted at the unchanged ledger: it reuses that exact authority,
preserves the Canonical Professor-to-Paper claim, returns Professor, and supports both directly
Canonical and evidence-subject-alias Web corroboration without accepting identity crosswires.
S8R5's displayed Patent-to-Company traversal is also Accepted: it replays applicant-only authority,
returns Company, preserves Patent-to-Company orientation, and protects inverse-view cap ordering
and Web identity boundaries. S8C now accepts the aggregate release-bound runtime and Tasks 8.3,
8.5, and 8.7: all seven lanes, fusion/rerank, sufficiency/supplemental execution, bounded Web
snapshots, and exact-release/exact-session read-only handle replay execute through the public
composition. Tasks 8.1/8.8 remain open for reviewed calibration and aggregate acceptance. S2C1 RED and
S2C2/Task 2.7 schema/corpus migration are Accepted, while S2C3/Task 2.8 remains pending. Aggregate
S2C must be Accepted before S8/S9 uses the corpus as an acceptance oracle. S10A/Task 10.1's
fixture-only knowledge-gap RED, S10B/Task 10.2's pure gap creation/classification GREEN, S10C/S10D's
offline-remediation mechanics, and S10O's durable PostgreSQL/admin/no-write closure are Accepted;
Tasks 10.3-10.5 are closed at `65/80`. S9A/Task 9.3, S8W/Task 8.4, S8S/Task 8.6, S8Q1's fixture-only Task 8.1
RED predecessor, S9M/Task 9.5, and S9G/Task 9.1 are Accepted fixture-only RED slices; S2C still
blocks only claim-level acceptance-oracle execution and Task 8.1 reviewed calibration, not
independent Ready fixture RED slices. Task 6.3 typed domain projection was Accepted at
`2026-07-13T09:56:27Z` in the
`canonical-v2-s2-baseline` worktree; the branch name is historical and no longer describes its
scope. It includes the four-domain projection/inclusion Modules, packaged catalog, PostgreSQL
Adapter, `C2_0009`, and focused tests. A 2026-07-13 no-external-database
run produced 178 passed, 118 skipped, 9 expected xfails, and 2 real failures: stale exact-head
coupling to `C2_0007`, and date-only versus instant validity representation at the S5/S6 interface.
S5G closed the latter without coercion; Task 6.3 replaced the permanent-head assertion with the
linear minimum-revision contract. The current pre-6.4 no-external-database run had 192 passed, 125
skipped, and 9 expected xfails with no real failure. Task 6.5 converted the nine relationship REDs
to GREEN and added C2_0010 persistence; Task 6.7 converted the five path-policy REDs to GREEN.
Aggregate S6 was Accepted at `2026-07-13T14:48:01Z`; S6R, aggregate S7, S2C1 RED, S2C2/Task 2.7,
S8C, S9I, S10O, S11A, the S9J public-answer-integrity correction, S11B, S11C/Tasks 11.1-11.5, and
S12A/Task 12.1 is Accepted, S2C3 review and Tasks 8.1/8.8/9.8 are retired, and S12B/Task 12.2 is a
verified functional Candidate. Tasks 12.3-12.6 remain open. Git
`main` fast-forwarded locally to the exact Accepted checkpoint `f0e6224` at
`2026-07-13T15:00:36Z`; no product database/index/release state changed and no push/cutover occurred.

## Accepted S11 consolidated Git baseline — 2026-07-22

- Exact recovery commit `8fd5f26c0749599860d4a08a26e6a9694d05a017` preserves every one of
  the 354 changed/nonignored source-worktree paths; aggregate import
  `641278f01b005c66bd356533d4df0fd11b678394` retains 299 formal implementation and acceptance
  paths while 55 preview-only paths remain in recovery.
- Successor correction `438c715190d4f8b5c2bbf9f29b6abe3899ec2330` makes the immutable S11C
  evidence relocation-safe. Current checkout paths locate bytes; frozen historical repository,
  cwd, basetemp, and temp-root fields are raw-hash-bound and compared lexically. No Accepted receipt,
  JUnit, ledger, screenshot, or collected-nodeid byte changed.
- Verification passed: strict OpenSpec; unique Alembic head `C2_0011`; 26 safe S7/S8 owners; 58
  S11C/S11B owners including relocation and tamper coverage; 7 current S11A Admin owners without the
  historical ignored root helper; focused Ruff check/format; archive/bundle/hash/scope/Git identity
  audits. The successor range passes `git diff --check`; the full imported range reports only four
  exact-hash-bound historical whitespace artifacts, retained verbatim rather than normalized. Exact
  evidence and path/hash inventory are in `git-consolidation-baseline-2026-07-22.md`.
- The branch `codex/canonical-v2-s11-consolidation` is Accepted as the sole local parent for future
  Ready slices. The Epic stays In Progress at `70/80`; Tasks 2.8, 8.1, 8.8, 9.8, and 12.1-12.6
  remain open. `main` remains `f0e6224`; S12, push, Cutover, and branch deletion remain unauthorized.

## S11C aggregate consumer acceptance — 2026-07-21T19:10:41Z

- Tasks 11.1-11.5 closed atomically at `70/80`. Exact S11A/S11B reruns, Accepted Task 2.7
  structural owners, interface/trace owners, `122` disposable-PostgreSQL cases, and `70` release/
  index cases are pass-only and machine-bound to persisted JUnit/collected-nodeid hashes.
- The guarded broad runs record `596` Admin nodeids with `18` failures plus `4` errors and `530`
  Canonical V2 predecessor nodeids with zero failure/error. All `22` rows reconcile exactly as
  `6 retired_replaced + 5 retired_reference_only + 11 unrelated_preexisting`; unaccounted and
  accepted-behavior failures are zero.
- The traceability repair preserves v1, binds four v2 predecessor reruns to exact repository cwd/
  UTC/command/output hashes, and recomputes both broad UTC windows from raw-hash-bound JUnit.
  Focused/full validator results are `1 passed` and `55 passed`; capture owner is `2 passed`.
- Static, strict OpenSpec, package/source-parity, generated cleanup, secret/scope, disposable-target,
  and frozen PostgreSQL/Milvus/forensic checks pass. Independent evidence and protected-scope
  reviews are `Critical=0 / Important=0 / Minor=0 / YAGNI=0`. Receipt SHA-256:
  `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`.
- S2C Task 2.8 remains only an S8/S9 acceptance-oracle gate. S12A/Task 12.1 is next. No Commit,
  Push, PR, Archive, promotion, original-source mutation, or Cutover occurred.

## S11B consumer migration and legacy quarantine acceptance — 2026-07-21T12:54:16Z

- The candidate application now exposes only the release-bound S11A chat, S10O gap operations, and
  one typed read-only four-domain admin runtime. Feedback binds the immutable server checkpoint;
  three explicit sanctioned CLIs cover accepted-restore evidence ingest, black-box chat smoke, and
  guarded baseline capture. V042 writers, direct SQL/retrieval, old collection assumptions, global
  readiness, direct active-index mutation, and the legacy React tree are quarantined from the
  candidate route/import/command graph.
- Focused current-byte evidence is `24 passed` for the agent quarantine/ingest/producer owners, `2
  passed` for the Admin consumer/smoke owners, `7 passed` for the S11A HTTP predecessor, and `1
  passed` for S10O operations. The guarded signature-v3 baseline records 530 Canonical V2 nodeids at
  exit `0` and 596 Admin nodeids at exit `1`, with 18 failures plus 4 setup errors retained for S11C,
  22/22 persisted-JUnit signatures independently replayed, 15 attributable blocked attempts, zero
  forbidden attempts, and complete owned-root cleanup.
- Exact route/inventory/script/React discovery, Ruff/format, `py_compile`, Pyright, strict OpenSpec,
  diff, package/source parity, and frozen original Postgres/Milvus/forensic checks pass. Final
  independent review is `Critical=0 / Important=0`; one shorthand-ID Minor is nonblocking. Receipt
  SHA-256: `cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945`.
- S11B changed no OpenSpec task or acceptance checkbox; the formal ledger remained `65/80`. Tasks
  11.1-11.5 remained open and S11C remained Specified at that historical checkpoint. No Commit,
  Push, PR, Archive, promotion, source/database/index write, or Cutover occurred.

## S9J public-answer-integrity correction acceptance — 2026-07-21T09:57:11Z

- One escaped `suppress_claims`/degradation class is closed across missing/conflicting selector
  failures, unresolved Web traversal, and blocking ambiguity: every unspecialized material gap now
  retains exactly one typed limitation and one bounded server-owned public sentence. Opaque SHA,
  canonical/reference identifiers, evidence/continuation IDs, and raw execution enums remain in
  structured audit fields and cannot become admitted public answer copy.
- The original pre-implementation terminal RED was not retained and is not reconstructed. The
  acceptance audit reproduced four exact branch failures plus three killed mutations before the
  shared repair. Final answer/multi-turn evidence is `29 passed`; existing answer owners are `9
  passed`, the corrected S11A HTTP owner is `7 passed`, the S9J/S11B/preview owner group is `11
  passed`, and the S10O UI owner is `1 passed`.
- Evidence ownership is explicit: the S11A HTTP owner proves the recorded missing-revenue gap and
  structured continuation; an executable Node harness proves the localized continuation label;
  the disposable `18190` real-data browser/API replay proves two bound turns, HTTPS Web evidence,
  desktop/mobile layout, clean console, and absence of opaque/operational public copy. Existing
  `18188/18189` preview listeners remained available.
- Ruff/format, `py_compile`, changed-scope Pyright, strict OpenSpec, and `git diff --check` pass.
  Final independent reviews have zero open Critical/Important findings; Minor/YAGNI are recorded
  and non-blocking. Receipt SHA-256:
  `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`.
- S9J changes no OpenSpec task or acceptance checkbox; the ledger remains `65/80`. S11B is the next
  execution slice. No Commit, Push, PR, Archive, promotion, source/database/index write, or Cutover
  occurred.

## S11A release-bound chat HTTP adapter acceptance — 2026-07-20T19:56:07Z

- The registered `POST /api/chat` now resolves one explicitly installed release-bound adapter and
  executes the real planner, `KnowledgeRead`, and `KnowledgeAnswer` with exact release validation,
  typed continuation selection, canonical displayed context, and no legacy SQL/fixed-handler
  fallback. Missing/wrong runtime fails closed with `503`.
- Compatibility mapping preserves the frozen HTTP schemas and executable `/browse#...` citation
  links while exposing bounded release/plan/lane/evidence/claim/citation/limitation/session traces.
  The answer-session fork, mapped response, public context/offer, and immutable feedback checkpoint
  commit atomically; every staged failure leaves prior state byte-identical.
- Exact RED was one xfail and one forced `_MissingS11AChatAdapter` failure. Final focused GREEN is
  `1 passed` with warnings denied; relevant predecessors are `26 passed`, S10O Admin is `1 passed`,
  and the four physical traversal owners are `4 passed`. The legacy chat signature is byte-identical
  at `250 passed, 7 failed, 3 skipped, 4 warnings` with canonical SHA-256
  `de88a0b8a64bba955d80fe06b8e54a1783a46fda36549f43c9cb11ac192bc959`.
- Complete Canonical V2 no-external evidence is `363 passed, 148 skipped` with three retained
  hostile-serializer warnings. Strictly guarded Admin evidence is `440 passed, 130 skipped, 8
  failed, 1 deselected, 12 warnings, 0 errors`; seven failures are the frozen legacy set and one is
  an unrelated pre-existing diff-clean `backend/api/domains.py`/quality-status-test call-order
  mismatch. S11A-related unexpected failures are zero. The unsafe dotenv-restored run is excluded.
- Ruff, non-legacy format, `py_compile`, Pyright `0 errors`, route/import guards, strict OpenSpec,
  diff/scope/secret/cache, locked-offline package/source parity, and protected-source checks pass.
  Two final reviews and two exception audits have zero open Critical/Important findings. Original
  Milvus/Postgres/forensic state remains exact. Receipt SHA-256:
  `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`.
- S11A changed no OpenSpec task or acceptance checkbox; the formal ledger remained `65/80` and
  Tasks 11.1-11.5 remained open for S11B/S11C at that historical checkpoint. No Commit, Push, PR,
  Archive, promotion, or Cutover
  occurred.

## S8C Tasks 8.3/8.5/8.7 aggregate runtime acceptance — 2026-07-20T10:50:22Z

- Exact TDD evidence was `1 xfailed` and one forced `_MissingS8CAggregateRuntimeClosure` failure for
  the seven absent release-bound ports. After pass-through existed, the second real RED was the
  public wrapper's `planner-owned plan has an unsupported interaction mode` rejection for an exact-
  binding handle replay.
- The final public vertical executes exact, structured, lexical, vector, relationship,
  internal-reference, and current-Web lanes through one release-bound service. It proves actual
  overlap, identity fusion before constraints/rerank, representative coverage, per-part
  sufficiency, bounded supplemental search, content-addressed snapshot admission, and read-only
  handle resolution with exact release/session binding and zero canonical/index/source-map writes.
- Final focused GREEN was `1 passed, 63 deselected`; detailed mechanics were `8 passed`; physical/
  release owners were `13 passed, 51 deselected`; complete no-external Canonical V2 was
  `351 passed, 141 skipped` with three already-documented hostile-model serializer warnings.
- Complete Ruff/format/Pyright/py_compile, strict OpenSpec, diff, offline lock, wheel source parity,
  scope/secret/cache/EOF, frozen Milvus, and paused-pgtest checks passed. The final negative-TTL
  probe closes the only implementation-review Important; targeted review is `C=0/I=0/M=0`.
- Tasks 8.3, 8.5, and 8.7 close atomically at `59/80`. Tasks 8.1 and 8.8 remain unchecked; S2C still
  gates only reviewed calibration and claim-level/provider aggregate acceptance. No Commit, Push,
  PR, Archive, promotion, Cutover, original-source write, or active-pointer mutation occurred.

## S9I Tasks 9.2/9.4/9.6 implementation acceptance — 2026-07-20T12:03:04Z

- The exact six-function owner first failed `6/6` only at the intended implementation seams. Four
  Important reviewer counterexamples plus one Minor were then added inside those same six functions,
  producing a second `5 failed, 1 passed` RED before repair.
- Final exact-owner evidence is `6 passed` with warnings denied; the complete answer owner matrix is
  `20 passed`, the relevant read predecessor matrix is `11 passed`, and complete no-external
  Canonical V2 is `357 passed, 141 skipped` with only the three intentional hostile-model serializer
  warnings.
- `KnowledgeAnswer` now fail-closes structured supported/conflicting/inference claims, never renders
  raw selector drafts, exposes accepted/degraded selector traces, builds evidence-relevant arbitrary
  per-turn assessment dimensions, resolves session referents through typed release-bound directives,
  and renders only bounded server-owned safety guidance. One owner passes an actual public
  `KnowledgeRead.execute` result into the answer seam.
- Complete Ruff/format/Pyright/py_compile, strict OpenSpec, diff, offline lock, wheel source parity,
  scope/secret/cache, frozen Milvus, and paused-pgtest gates pass. The final frozen-hash independent
  review is `C=0/I=0/M=0/YAGNI=0`.
- Tasks 9.2, 9.4, and 9.6 close atomically at `62/80`. Task 9.8 and aggregate S9 remain unchecked;
  S2C still gates only reviewed claim-level/provider/latency acceptance. No Commit, Push, PR,
  Archive, promotion, Cutover, original-source write, or active-pointer mutation occurred.

## S10O Tasks 10.3/10.4/10.5 durable operations acceptance — 2026-07-20T13:25:40Z

- Exact initial RED was seven absent durable-module failures plus one absent V2-admin-router failure.
  Six independent-review categories were then encoded into the same eight owner functions, producing
  focused counterexample RED before repair.
- C2_0011 and the explicit-target adapter provide append-only gap/transition history, deterministic
  replay and concurrency behavior, complete searchable-column/payload/hash revalidation, and exact
  Accepted release/build-manifest/effect truth. Bounded V2-only admin list/detail operations expose
  honest assertions, decisions, releases, provenance, unresolved IDs, filters, ordering, and pages.
- Final real disposable PostgreSQL plus online evidence is `7 passed` with warnings denied; unchanged
  S10A-S10D is `8 passed`; the V2 admin owner is `1 passed`; complete no-external Canonical V2 is
  `357 passed, 148 skipped` with only three pre-existing hostile-model serializer warnings.
- The real online Read-to-Answer-to-gap path and separate offline linked-to-resolved rehearsal mutate
  only append-only `ops.*` rows. Canonical/relationship assertions and decisions, release/manifest/
  active state, index adapter calls, and original Milvus remain byte-identical.
- Complete Ruff/Pyright/py_compile, strict OpenSpec, diff, single migration head, offline lock/wheel
  source parity, JavaScript, scope/import-quarantine, disposable cleanup, frozen Milvus, and paused-
  pgtest gates pass. Final frozen-hash review is `C=0/I=0`; Minor/YAGNI are nonblocking.
- Tasks 10.3, 10.4, and 10.5 close atomically at `65/80`. No Commit, Push, PR, Archive, promotion,
  Cutover, original-source write, or active-pointer mutation occurred.

The code-grounded continuation plan is
`.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`.

## S8R5 displayed Patent-to-Company applicant traversal acceptance — 2026-07-20T09:38:32Z

- S8R5 maps only `company_has_patent/patent_to_company/patent -> company` to exact accepted current
  `patent_has_applicant@canonical-v2-relationship-v1` authority. The displayed Patent is the source
  witness, the returned identity is Company, and applicant is never relabeled as owner, assignee,
  inventor, or a generic organization relation.
- The dedicated trace replays the complete S8R2 candidate/assertion/decision/current/retained-
  source/PatentApplicant/public-projection/paired-eligibility chain. Internal Company-to-Patent
  replay uses the finite authoritative current count; the caller result cap applies only after the
  exact displayed Patent is retained.
- Review repair added the core ordering and Web identity matrix: authority count two with caller cap
  one still returns Company; a same-Company Web alias fuses; a direct Canonical object crosswire
  becomes invalid Web output while local evidence survives; another Canonical Company subject fails
  release-bound postvalidation.
- Final evidence is focused warnings-as-errors `1 passed, 62 deselected`, exact relationship matrix
  `6 passed, 57 deselected`, and complete no-external Canonical V2 `350 passed, 141 skipped`, plus
  three intentional hostile-model serializer warnings. Complete Ruff/format/compile, Pyright
  (`0/0/0`), strict OpenSpec, diff/whitespace, offline wheel/source parity, secret/xfail scan,
  generated-output cleanup, and frozen-target checks pass.
- Acceptance receipt:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r5/verification-receipt.json`. Final
  targeted review reports `C=0/I=0/M=0/YAGNI=0`. Task 8.3 and the formal `56/80` ledger remain
  unchanged; no provider, original source/database/index, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed.

## S8R4 displayed Paper-to-Professor attribution traversal acceptance — 2026-07-20T08:53:38Z

- S8R4 maps only `professor_authored_paper/paper_to_professor/paper -> professor` to inverse replay
  of exact accepted current `professor_attributed_to_paper@canonical-v2-relationship-v1` authority.
  It returns Professor while the protected displayed Paper remains a source witness and the
  Canonical claim remains Professor-to-Paper.
- The dedicated trace binds the complete S8R3 relationship, assignment, decision, retained-source,
  public-projection, paired eligibility, release, and evidence chain. Internal forward replay uses
  the finite authoritative current-relationship count; the caller result cap applies only after
  exact displayed-Paper filtering, preventing false zero results.
- The final trust boundary distinguishes direct `canonical`, alias-bearing `web_candidate`, and
  unresolved `web_only` states. Direct Canonical evidence binds the exact object; an Accepted Web
  alias may retain its evidence subject while fusing to the local Professor; unknown/inconsistent
  states and another Canonical Professor subject fail closed. Local evidence alone owns the
  Professor-Paper relation and displayed-Paper witness.
- Final evidence is focused warnings-as-errors `1 passed, 61 deselected`, exact relationship matrix
  `5 passed, 57 deselected`, and complete no-external Canonical V2 `349 passed, 141 skipped`, plus
  three intentional hostile-model serializer warnings. Complete Ruff/format/compile, Pyright
  (`0/0/0`), strict OpenSpec, diff/whitespace, offline wheel/source parity, secret/xfail scan,
  generated-output cleanup, and frozen-target checks pass.
- Acceptance receipt:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r4/verification-receipt.json`. Final
  independent review reports `C=0/I=0/M=0/YAGNI=0`. Task 8.3 and the formal `56/80` ledger remain
  unchanged; no provider, original source/database/index, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed.

## S8R3 displayed Professor-to-Paper attribution traversal acceptance — 2026-07-20T02:13:12Z

- S8R3 maps only `professor_authored_paper/professor_to_paper/professor -> paper` to exact
  accepted current `professor_attributed_to_paper@canonical-v2-relationship-v1` authority. It
  returns Paper while the protected displayed Professor remains a source-side witness; it does not
  infer `paper_has_author`, authorship prose, Person/name/ORCID links, or Paper existence state.
- The dedicated trace binds the shared source assertion, exact Professor/Paper assignments,
  decision input/outcome/current decision, retained source record, both public projections, paired
  direction-bound path eligibility, Paper identity status, complete evidence envelope, and all
  content-derived IDs/hashes. Unsupported multi-reference members are omitted under honest
  representative open-world coverage.
- Review-driven RED/GREEN closed same-Paper Web constraint replay, fabricated Web relationship
  claims, fused provenance, complete receipt/handle ownership, shared endpoint entity-type,
  retained/shared source-record continuity, and the Candidate-review path/lane bypass. Public
  invalid source/path/policy requests, including a retained relationship path with its relationship
  lane removed, fail before Web effects; an unknown current-release Professor remains a local zero
  and the independent Web lane may still run.
- Fresh Candidate evidence is focused warnings-as-errors `1 passed, 60 deselected`, exact
  predecessors `9 passed, 52 deselected`, physical/release owner `59 passed, 2 skipped`,
  relationship/publication owners `15 passed`, KnowledgeRead/planning owners `17 passed`, and
  complete no-external Canonical V2 `348 passed, 141 skipped`, plus three intentional hostile-model
  serializer warnings. Ruff/format/compile, Pyright (`0/0/0`), strict OpenSpec, diff/whitespace,
  offline wheel/source parity, scoped secret/xfail scan, and frozen-target checks pass.
- Acceptance receipt:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r3/verification-receipt.json`.
  Final implementation, targeted spec-repair, and evidence reviews report
  `C=0/I=0/M=0/YAGNI=0` and allow acceptance. Task 8.3 and the formal `56/80` ledger remain
  unchanged; no provider, original source/database/index, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed.

## S8R2 displayed Company-to-Patent applicant traversal acceptance — 2026-07-19T22:19:19Z

- S8R2 maps the planner's `company_has_patent/company_to_patent/company -> patent` path only to the
  reverse traversal of exact accepted current `patent_has_applicant@canonical-v2-relationship-v1`
  authority. Applicant is never relabeled as owner, assignee, inventor, or a generic organization;
  the displayed Company is a protected source witness while the returned identity remains Patent.
- The release-owned trace binds candidate, typed assertion, outcome, typed/current decision,
  retained/public source record, observed/source-event and validity time, Patent applicant
  subobject, Company/Patent projections, and both direction-bound eligibility results. Valid
  authoritative-zero, nonmatching nonzero authority, endpoint exclusion, max-zero, and target-
  constraint rejection remain distinct from invalid source/path/policy authority.
- Review-driven RED/GREEN closed quality-flag ordering, duplicate/cross-lane ownership, Web Company
  witness, top-level evidence, auxiliary, coverage, envelope, constraint-rejection, and legitimate
  same-Patent Web-fusion findings. Final independent reviews report zero Critical/Important; one
  wording Minor is recorded and nonblocking.
- Final evidence is exact predecessors `8 passed`, physical/release owner `58 passed, 2 skipped`,
  relationship/publication owners `15 passed`, KnowledgeRead/planning owners `17 passed`, and
  complete no-external Canonical V2 `347 passed, 141 skipped`, plus three intentional hostile-model
  serializer warnings. Complete Ruff/format/compile, Pyright (`0/0/0`), strict OpenSpec, diff,
  offline wheel/source parity, scope/secret/cache, and frozen-target gates pass. The secret-free
  receipt is `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r2/verification-receipt.json`.
- Task 8.3 and aggregate S8 remain open at formal `56/80`. No provider, source/original database or
  index, active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. S2C3C2 still gates
  only reviewed calibration/oracle execution, not the next independently Ready deterministic slice.

## S8R1 release-scoped Technology relationship traversal acceptance — 2026-07-19T20:05:54Z

- S8R1 carries omission-preserving relationship paths plus Technology-only reference queries into
  the relationship lane and installs its in-memory adapter only for the exact S7K relationship pair
  plus the replayed S7 index/internal-reference authority. Authoritative zero remains supported;
  legacy no-pair zero remains non-authoritative and unsupported for traversal.
- The adapter executes exactly `technology_route -> company` for discussion/mention, claimed
  adoption, and demonstrated use. Each result binds the current relationship, retained public
  assertion/source identity, route-owned Technology anchor, Product subobject, parent Company, and
  `verified_relationship_traversal` decision. The claim subject remains the Product stable
  reference; Company identity is only a result locator and Product capability is never inferred.
- Exact RED/GREEN was `1 xfailed` followed by `1 passed`; review-driven regressions closed all seven
  Important contract/code issues, including request-time identity, hostile fused-output ownership,
  required freshness flags, trace identity, and duplicate auxiliary traces. Final independent
  re-reviews report zero Critical/Important/Minor/YAGNI with `Accept`.
- Final evidence is corrected predecessors `13 passed`, physical/release owner `56 passed, 2
  skipped`, relationship/publication owners `15 passed`, KnowledgeRead/planning owners `17 passed`,
  and complete no-external Canonical V2 `345 passed, 141 skipped`, plus three intentional hostile-
  model serializer warnings. Complete Ruff/format/compile, Pyright (`0/0/0`), strict OpenSpec,
  diff/whitespace, offline wheel/source parity, scope/secret/cache, and frozen-target gates pass.
  The secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r1/verification-receipt.json`.
- Task 8.3 and aggregate S8 remain open at formal `56/80`. No provider, source/original database or
  index, active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. A fresh dependency
  audit selects the next smallest real relationship family; S2C3C2 still gates only reviewed
  calibration/oracle execution.

## S7K relationship publication authority correction acceptance — 2026-07-19T17:05:53Z

- S7K deepens only `IsolatedReleaseBundle`: a present relationship request/result pair is exact-
  replayed through the installed combined registry, must carry its internal-reference graph, and
  replays the same four-public/three-internal projection manifests as the release. The relationships
  section binds its role, release, projection schema, accepted current count, and complete result
  hash. A no-pair zero section remains legacy compatibility only; an authoritative zero release
  retains a present pair.
- Publication preflight accepts only the exact bundle type, reconstructs fresh typed copies,
  recomputes the complete build-manifest hash, and uses only those copies before backup-gate,
  target/index, state, or PostgreSQL registry effects. The hostile matrix proves zero effects for
  partial/absent/cross-wired pairs, missing internal authority, wrong registry/release/as-of,
  replay mismatch, legacy-zero section drift, all five relationship-section axes, seven-manifest
  drift, stale full hash, and subclass/model-construct bypasses.
- Exact TDD was `1 xfailed`; forced RED was the direct
  `_MissingS7KRelationshipPublicationAuthority` before fixture or external-target acquisition;
  focused GREEN is `1 passed` with warnings treated as errors. Initial contract reviews closed six
  Important findings. Independent implementation review found and closed two Important section-
  role/effect-coverage gaps; targeted re-review reports zero Critical/Important/Minor/YAGNI with
  `Accept`.
- Final evidence is focused/predecessor `1/7 passed`, shared physical/release owner `55 passed, 2
  skipped`, release interface `6 passed`, relationship persistence `19 passed` against a newly
  created and removed disposable PostgreSQL container, and complete no-external Canonical V2 `344
  passed, 141 skipped`, plus three intentional hostile-model serializer warnings. Complete Ruff/
  format/compile, Pyright (`0/0/0`), strict OpenSpec, `git diff --check`, locked offline wheel/source
  parity, scope/secret/cache, and frozen-target gates pass. The secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7k/verification-receipt.json`.
- Task 8.3 and aggregate S8 remain open at formal `56/80`. No provider, source/original database or
  index, active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. S8R1 release-
  scoped relationship retrieval is next; S2C3C2 still gates only reviewed calibration/oracle
  execution.

## S8IR1 release-scoped internal-reference lookup acceptance — 2026-07-19T16:07:14Z

- S8IR1 copies typed `internal_reference_queries` only into its lane request and installs one real
  isolated adapter only with the paired index-request/institution-catalog replay authority. It
  verifies all four planning-binding hashes before effects, audits exact Person/Technology lookup
  documents, and postvalidates returned evidence/fusion/handles from the in-memory release graph
  without reopening physical storage.
- Resolved Person matches are filtered by exact education, Company-role, and geography facts;
  unresolved/nonmatching and valid zero-match Person queries remain trace-only. Technology output
  carries only the exact internal route definition plus a separately bound public-origin locator;
  it does not claim discussion, adoption, use, Product capability, or traversal authority.
- Exact TDD was `1 xfailed`; forced RED was the direct
  `_MissingIsolatedInternalReferenceLookupAdapter` before fixture acquisition; focused GREEN is
  `1 passed` with warnings treated as errors. Independent review found one Important zero-match
  Person lane failure; the focused regression reproduced and closed it, and targeted re-review is
  zero Critical/Important/Minor/YAGNI with `Accept`.
- Final evidence is focused/predecessor `9 passed`, complete physical/release owner `54 passed, 2
  skipped`, KnowledgeRead plus query-planning owners `17 passed`, and complete no-external
  Canonical V2 `343 passed, 141 skipped`, plus three intentional hostile-model serializer warnings.
  Complete Ruff/format/compile, Pyright (`0/0/0`), strict OpenSpec, `git diff --check`, locked
  offline wheel/source parity, scope/secret/cache, and frozen-source/target gates pass. The
  secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8ir1/verification-receipt.json`.
- Task 8.3 and aggregate S8 remain open at formal `56/80`. No provider/network, persistence,
  source/index/database, pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. A
  release-bound relationship adapter still requires the named S7 relationship-publication
  authority correction; that local prerequisite does not block independent Ready work.

## S8V2 Professor typed vector-view selection acceptance — 2026-07-19T14:45:45Z

- S8V2 carries one finite `professor_vector_view` from the exact recorded proposal through a
  nonblocking planner-owned plan into only its vector `LaneRequest`. It requires the selector for
  Professor+vector recorded/release-bound execution, preserves omission and literal hashes for
  existing unbound values, and rejects real isolated omission before physical or embedding effects.
- The audited S8V1 adapter now filters identity, research, or both Professor points before scoring
  and the unchanged raw-point bound. Research display identity comes only from one structurally
  unique same-release Professor public identity lookup document whose manifest, canonical ID,
  typed projection hash, and point source hash agree. Release post-validation rejects unselected
  views and forged fused/handle display names without reopening physical storage.
- Exact TDD was `1 xfailed`; forced RED was the direct
  `_MissingProfessorVectorViewSelection` before fixture acquisition; focused GREEN is `1 passed`
  with warnings treated as errors. Independent review found one Important different-source
  duplicate-authority bypass; the same group reproduced it, structural-uniqueness-before-hash
  repair closed it, and targeted re-review reports zero Critical/Important/Minor/YAGNI.
- Final evidence is focused/predecessor `8 passed`, complete physical/release owner `53 passed, 2
  skipped`, KnowledgeRead plus query-planning owners `17 passed`, and complete no-external
  Canonical V2 `342 passed, 141 skipped, 0 xfailed`, plus the three intentional hostile-model
  serializer warnings. Complete Ruff/format/compile, Pyright (`0/0/0`), strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target gates pass. The secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8v2/verification-receipt.json`.
- Task 8.3 and aggregate S8 remain open at formal `56/80`. No provider/network, persistence,
  source/index/database, pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. S8IR1
  release-scoped internal-reference lookup/filter is the next independent real-lane slice.

## S8V1 release-scoped vector retrieval acceptance — 2026-07-19T10:16:54Z

- S8V1 adds one package-internal audited vector adapter and installs it in the Accepted S8E1
  composition only when an explicit release-model embedding port is supplied. It validates the
  complete marked physical snapshot against every bound bundle axis, scores only accepted public
  points with deterministic finite cosine, filters domains/displayed IDs/exclusions, retains S7J
  eligibility effects, and emits a content-bound `LocalVectorTrace` under the unchanged
  `local_projection_trace` key. Professor requests remain fail-closed until S8V2 supplies the typed
  identity/research/both plan selector.
- Exact TDD was `1 xfailed`; forced RED was one direct
  `_MissingIsolatedVectorRecallAdapter`; focused GREEN is `1 passed`. Review-driven RED/GREEN closes
  receipt-target identity and the one Important opaque-authority gap: release-bound
  `KnowledgeRead.execute` now checks complete point/target/manifest/publication lineage and
  recomputes query embedding plus cosine/score, so self-consistent query-embedding, source-
  projection, and score mutations cannot escape the public seam.
- Final evidence is predecessor matrix `8 passed`, complete physical/release owner `51 passed, 2
  skipped`, KnowledgeRead matrix `17 passed`, and complete no-external Canonical V2 `340 passed,
  141 skipped, 0 xfailed`, plus the three intentional hostile-model serializer warnings. Complete
  Ruff/format/compile, Pyright (`0/0/0`), strict OpenSpec, `git diff --check`, locked offline wheel/
  source parity, scope/secret/cache, and frozen-source/target gates pass.
- Final independent review reports zero Critical/Important, one nonblocking broad-exception-test
  Minor, zero YAGNI, and verdict `Accept`. The secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8v1/verification-receipt.json`.
- Task 8.3 and aggregate S8 remain open at the unchanged formal `56/80` ledger. No external
  provider/network, persistence, source/index/database, pointer, Commit, Push, PR, Archive,
  promotion, or Cutover changed. S8V2 Professor typed vector-view selection is the next named
  successor.

## S8P2 planning taxonomy and assessment intent acceptance — 2026-07-19T07:28:02Z

- S8P2 completes Task 8.2 through the existing release-bound `QueryPlanner.plan` seam. It adds a
  finite recorded-proposal taxonomy and cross-field matrix, server-owned official-Web allowlisting
  and bounded budgets, proposal-to-plan material-question parts, one open lightweight
  `AssessmentIntent`, malformed same-class proposal revalidation, and information-only ambiguity
  derivation while preserving frozen S8P1 omission/hash identities.
- Initial exact TDD was `2 xfailed, 52 deselected`, forced RED was `2 failed, 52 deselected` at the
  two named sentinels, and GREEN was `2 passed, 52 deselected`. The first independent review found
  zero Critical and four Important issues; review-driven RED reproduced all four classes plus the
  absent material-parts contract, and repaired GREEN returned `2 passed, 52 deselected`.
- Final owner evidence is: query planning `5 passed`; S8P1 focused `2 passed`; shared physical/
  release `47 passed, 2 skipped`; KnowledgeRead matrix `17 passed`; KnowledgeAnswer matrix
  `13 passed`; complete no-external Canonical V2 `336 passed, 141 skipped, 0 xfailed`. Ruff,
  format/compile, complete Pyright (`0 errors, 0 warnings, 0 informations`), strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-target gates
  pass.
- Targeted re-review and a fresh final independent review each report zero Critical/Important and
  verdict `Accept`. Minor/YAGNI notes are recorded without blocking. The content-bound receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p2/verification-receipt.json`.
- Task 8.2 alone is checked, moving the formal ledger from `55/80` to `56/80`; `acceptance.md` is
  unchanged. No provider, persistence, database/index/source, active pointer, Commit, Push, PR,
  Archive, promotion, or Cutover changed. S2C3C2 remains only the external reviewed-oracle gate for
  Task 8.1 calibration and later S8/S9 claim-level acceptance execution, not a global goal blocker.

## S8E1 release-bound KnowledgeRead composition acceptance — 2026-07-19T08:08:07Z

- S8E1 adds one package-internal `create_isolated_release_knowledge_read` composition root. Callers
  supply only the bounded Universal-Web port/policies; the factory owns the existing real physical
  exact/structured adapters and delegates through the sole public `KnowledgeRead.execute` seam.
  Every plan is exact-revalidated and its execution-relevant release, publication state/hash/
  evidence, manifest, and index-result binding must match before any physical or Web call. Missing,
  cross-wired, or unsupported local lanes fail as configuration errors rather than provider
  degradation.
- Exact TDD was `1 xfailed, 49 deselected`, forced RED was `1 failed, 49 deselected` at
  `_MissingIsolatedReleaseKnowledgeReadFactory`, and GREEN is `1 passed, 49 deselected`.
  Review-driven hardening independently mutates every owned binding axis, uses explicit reader/Web
  spies for fail-before-effect, rejects invalid Universal-Web bounds, and proves accepted/oversize/
  missing snapshot receipts while exact/structured local evidence remains available.
- Final evidence is: predecessor-focused `6 passed, 44 deselected`; complete physical/release owner
  `48 passed, 2 skipped`; KnowledgeRead matrix `17 passed`; complete no-external Canonical V2
  `337 passed, 141 skipped, 0 xfailed`. Complete Ruff, format/compile, Pyright (`0/0/0`), strict
  OpenSpec, `git diff --check`, offline wheel/source parity, scope/secret/cache, and frozen-target
  checks pass.
- The final independent review reports zero Critical/Important/Minor/YAGNI and verdict `Accept`.
  The content-bound receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8e1/verification-receipt.json`.
- Task 8.3 remains open and the formal ledger remains `56/80`; lexical, vector, relationship, and
  internal-reference real adapters remain downstream. No external provider/network, persistence,
  database/index/source, active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed.
  S8L3 release-scoped lexical lookup is the next smallest Ready target.

## S8L3 release-scoped lexical lookup acceptance — 2026-07-19T08:35:45Z

- S8L3 adds the first real lexical lane to the Accepted S8E1 composition without exposing a caller
  adapter map. One non-empty NFKC/casefold/whitespace-normalized phrase must occur within typed
  public projection scalar content. The adapter strips only one exact trailing `[lane=lexical]`
  marker and one matched curly or ASCII double-quote pair; it adds no ranking, stemming, synonym,
  stopword, threshold, provider, or persistence framework.
- Exact TDD was `1 xfailed, 50 deselected`, forced RED was `1 failed, 50 deselected` at
  `_MissingIsolatedLexicalLookupAdapter`, and focused GREEN is `1 passed`. Review-driven hardening
  closes the exact-name shortcut, pre-read release/domain gaps, and finite quote/marker/
  normalization loophole with a no-protected-slot proper substring probe and compact positive/
  negative literal matrix.
- Final evidence is: predecessor-focused `6 passed`; complete physical/release owner `49 passed,
  2 skipped`; KnowledgeRead matrix `17 passed`; complete no-external Canonical V2 `338 passed,
  141 skipped, 0 xfailed`, plus the three intentional hostile-model serializer warnings. Complete
  Ruff, format/compile, Pyright (`0/0/0`), strict OpenSpec, `git diff --check`, locked offline wheel/
  source parity, scope/secret/cache, and frozen-target checks pass.
- Final independent review reports zero Critical/Important and verdict `Accept`. One nonblocking
  Minor records the absence of a dedicated multi-hit lexical ordering probe; deterministic ordering
  still reuses the Accepted shared candidate ordering. The secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8l3/verification-receipt.json`.
- Task 8.3 remains open and the formal ledger remains `56/80`; vector, relationship, and internal-
  reference real adapters remain downstream. No external provider/network, persistence, database/
  index/source, active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. S8V1
  release-scoped vector retrieval is the next candidate Slice.

## S7J vector eligibility lineage correction acceptance — 2026-07-19T09:11:49Z

- The S8V1 design gate found one material Accepted-S7 omission: public vector points retained only
  semantic policy version and undifferentiated evidence IDs, so a read adapter could not preserve
  exact decision ID, outcome, or visible limitations. S7J adds those exact replayed effects to each
  public point; internal Person/Technology points remain decision-free admitted auxiliaries.
- Builder manifests and `ReleasePublication` now consume one production-owned canonical hash of the
  complete typed point envelope. The review-driven RED locks every required field family with a
  fourteen-row valid mutation matrix and proves equal mutated expected/actual points plus identical
  old manifests are rejected only by expected/actual inventory evidence, with zero point or manifest
  discrepancies.
- Exact TDD was `1 xfailed`; forced RED was one direct
  `_MissingS7JSemanticEligibilityLineage`; focused GREEN and S7I were each `1 passed`. Final owner
  evidence is release publication `6 passed`, S8 physical successors `4 passed`, complete physical/
  release `50 passed, 2 skipped`, and complete no-external Canonical V2 `339 passed, 141 skipped,
  0 xfailed`, plus the three intentional hostile-model serializer warnings.
- Complete Ruff, format/compile, Pyright (`0/0/0`), strict OpenSpec, `git diff --check`, locked
  offline wheel/source parity, scope/secret/cache, and frozen-target checks pass. Final independent
  review is zero Critical/Important/Minor/YAGNI and `Accept`; the secret-free receipt is
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7j/verification-receipt.json`.
- S7J changes no point population/ID/content/vector, Milvus schema, policy semantics, release
  pointer, Task checkbox, or formal `56/80` ledger. No Commit, Push, PR, Archive, promotion, or
  Cutover occurred. S8V1 release-scoped vector retrieval may now proceed.

## S7I lookup-eligibility lineage correction acceptance — 2026-07-16T04:55:58Z

- The S8L1 design gate found one material S7 projection omission: public lookup documents retained
  only the path-policy version, not the replay-validated exact decision, outcome, or visible
  limitations. S7I adds those three typed fields, preserves decision-free admitted internal
  auxiliaries, and binds the complete normalized document envelope into manifest parity without
  changing document populations, IDs, lookup content, policy semantics, or any public S7 method.
- Exact TDD evidence is one intended RED at missing `eligibility_decision_id`, then one focused
  pass. The complete shared S7 owner returned `42 passed, 2 skipped`; S7 sibling owners returned
  `14 passed`; complete no-external Canonical V2 returned `330 passed, 141 skipped, 0 xfailed`.
  Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, wheel/source parity, scope/secret/cache, and frozen-source checks pass.
- The independent merged review reran the focused and shared-owner checks and reported zero
  Critical, Important, Minor, and YAGNI findings. S7I is Accepted without reopening historical S7
  evidence or changing the formal 55/80 ledger. S8L1 may now bind a real read to an
  `IsolatedReleaseBundle`; the receipt is under the S7I run directory.

## S8L1 release-scoped physical exact lookup acceptance — 2026-07-16T05:31:12Z

- S8L1 composes the existing `KnowledgeRead` exact lane with one same-class revalidated
  `PublishedRelease` plus `IsolatedReleaseBundle`. Every call uses the real guarded S7 reader and
  requires exact physical equality with the bundle's accepted lookup-document snapshot before any
  mapping. Only four public domains are eligible; internal Person/Technology auxiliaries remain
  excluded. Typed projection JSON, release/object/domain/source hashes, exact eligibility decisions
  and limitations, bundle/target/manifest/index identities, publication evidence, candidate IDs,
  evidence IDs, and item/candidate trace axes are content-bound and cross-validated.
- Exact TDD was `1 xfailed` and one forced missing-module failure, followed by focused `1 passed`.
  The unchanged S7 physical node plus S8L1 returned `2 passed`; the complete shared file returned
  `43 passed, 2 skipped`; all 16 existing KnowledgeRead owners passed; complete no-external
  Canonical V2 returned `331 passed, 141 skipped, 0 xfailed` with the three existing hostile-model
  warnings. Complete Ruff, format, compile, Pyright, strict OpenSpec, diff, wheel/source parity,
  scope/secret/cache, and frozen-target gates pass.
- The merged review found three Important issues in query-text fallback, empty/cross-domain output,
  and non-identity excluded terms. Each was reproduced, repaired, and regression-covered; targeted
  re-review closed all three with zero new Critical/Important. The source-authority naming Minor and
  redundant state-check YAGNI are recorded but nonblocking. S8L1 is Accepted at the unchanged 55/80
  ledger; Task 8.3 and aggregate S8 remain open. The secret-free receipt is under the S8L1 run
  directory.

## S8L2 release-scoped displayed-set structured lookup acceptance — 2026-07-16T06:17:22Z

- S8L2 reuses S8L1's same-class `PublishedRelease`/`IsolatedReleaseBundle`, real guarded lookup
  readback, exact bundle snapshot equality, four-domain typed projection validation, internal-
  auxiliary exclusion, and eligibility lineage. It adds only the structured displayed-set lane:
  empty sets return before read, protected-set disagreement fails before read, and exact Canonical
  members are filtered by requested public domains, complete typed-content exclusions, and candidate
  bounds. `LocalProjectionTrace.execution_lane` separates exact and structured identities while the
  default exact lane preserves its prior raw/evidence/content identities and serialized replay.
- Exact RED was `1 xfailed` and one forced missing-adapter failure, followed by focused `1 passed`.
  The unchanged S8L1 focused group is `1 passed`; the complete shared file is `44 passed, 2 skipped`;
  all 16 KnowledgeRead owners pass; complete no-external Canonical V2 is `332 passed, 141 skipped,
  0 xfailed` with the three existing hostile-model warnings. Complete Ruff/format/compile/Pyright,
  strict OpenSpec, diff, wheel/source parity, scope/secret/cache, and frozen-target gates pass. The
  fresh 276-entry wheel at `/var/tmp/canonical-v2-s8l2-wheel-20260716T061359Z/` has SHA-256
  `081046b91078e918f006e126f7eae01af358c7c3c5eebe87d554cc3c8064dcd9`, contains both read modules,
  excludes tests/`.agents`, and matches source hashes.
- The merged review found two Important test-integrity gaps: legacy exact evidence/serialization
  compatibility and service-level model-valid cross-lane rejection. Both were repaired in the one
  allowed test, and a mechanical format-gate failure was reproduced and formatted. Final targeted
  re-review is zero Critical/Important/Minor/YAGNI. S8L2 is Accepted at the unchanged 55/80 ledger;
  Tasks 8.3/8.5 and aggregate S8 remain open. The secret-free receipt is under the S8L2 run directory.

## S8P1 release-bound query planner acceptance — 2026-07-16T08:02:11Z

- S8P1 binds the existing query-planning seam to one same-class revalidated serviceable publication,
  complete isolated S7 bundle, exact replayed index/candidate/internal graph, recomputed manifest
  hash, exact release-observed institution catalog, and validated four-domain/lane policy. Resolved
  and unresolved Person records plus Technology routes are derived only from accepted typed
  projections/evidence; internal references remain non-public. The returned plan carries one
  content-bound release trace while unbound legacy plan JSON and content hashes remain byte/value
  identical.
- Exact RED was `2 xfailed, 46 deselected` and forced execution was two direct missing-factory
  failures. Final focused/shared/query-owner/read-owner/full results are `2 passed`, `46 passed, 2
  skipped`, `4 passed`, `16 passed`, and `334 passed, 141 skipped, 0 xfailed`; the three full-suite
  warnings are the existing hostile-model serializer warnings. Complete Ruff/format/compile/Pyright,
  strict OpenSpec, diff, fresh offline wheel/source parity, scope/secret/cache, and frozen-target
  gates pass.
- Review-driven repairs close valid manifest-order comparison, bound-plan catalog/release/public-
  population cross-wires, multi-Company fact Cartesian matching, authoritative Technology lineage,
  exact evidence/hash assertions, and missing/shared institution-alias coverage. Targeted re-review
  reports zero Critical/Important. S8P1 is Accepted at the unchanged `55/80` ledger; Task 8.2 stays
  open and S8P2 is the next Ready successor. No provider, persistence, database/index/source, active
  pointer, Commit, Push, PR, archive, promotion, or Cutover changed.

## ADR-013-ADR-022 reconciliation gate — 2026-07-13T17:44:15Z

- The user selected each ADR decision during the requirements grill, confirmed that the Spec should
  be finalized, and then explicitly instructed this Canonical V2 goal to continue. That sequence is
  the recorded user review for this contract gate; it is not implementation or cutover acceptance.
- Independent review round one found two Critical and five Important gaps. Corrections added
  mandatory Person materialization for resolved evidence, Person typed-filter retrieval, Technology
  alias/route comparison, scoped/as-of Industry Brief answers, exact S6R/S2C/S7 dependencies,
  historical S2 preservation, calibrated G ambiguity, Web-handle lifecycle cases, and explicit hard
  invariants.
- Independent re-review found three Important consistency residues; mandatory ambiguity switching,
  non-adoption discussion-or-mention semantics, and ADR S6R/S2C phase ownership were aligned. Final
  re-check returned `Ready: Yes` with zero open Critical/Important findings.
- `openspec validate rebuild-canonical-v2-knowledge-platform --strict` passed; `git diff --check`
  passed. The task ledger remains 36/80 because this gate changes no implementation checkbox.
- S6R1/Task 6.9 is the only critical-path implementation slice made Ready. S6R2+ and all S7 work
  remain Specified/blocked; S2C may be separately contracted without sharing a writer.

## S6R1 Task 6.9 internal-reference RED acceptance — 2026-07-13T18:21:59Z

- Seven strict RED groups freeze the additive internal-reference catalog and manifest scope seam,
  role-neutral Person materialization from resolved Professor/company-personnel/Paper-author/
  Patent-inventor evidence, unresolved same-name Person non-materialization, Technology concept/
  route lineage, exact discussion-or-mention versus claimed-adoption versus demonstrated-use
  relationship IDs, exact v1/v2 relationship coexistence, explicit internal endpoint registry, and
  the four-public-domain/Product-capability negatives.
- Masking is exact. Normal focused RED returned `7 xfailed in 5.18s`, exit 0. Forced RED with
  `--runxfail` returned `7 failed in 5.14s`, expected exit 1; failures were the named missing
  `PACKAGED_REFERENCE_CATALOG`/`ProjectionScope`/internal-reference Module/relationship-registry
  contracts, not nested imports or unrelated dependencies.
- Existing `test_domain_inclusion_contract.py`, `test_domain_projection_contract.py`, and
  `test_path_eligibility_contract.py` returned `45 passed in 6.03s`, proving the accepted four-domain
  and path behavior was unchanged.
- Ruff check and format passed for both new files; app-environment Pyright returned `0 errors, 0
  warnings, 0 informations`. Strict OpenSpec and `git diff --check` passed. Production-source scope,
  high-confidence secret, and generated-cache checks were clean.
- Historical `build_domain_catalog.py --check` failed only with the already-recorded
  `authority source hash changed: openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md`.
  This is expected correction evidence: S6R2 owns an additive catalog bound to exact v1 content/file
  hashes and may not rewrite or hash-only rebind the accepted v1 artifact.
- The original independent review found five Important test-depth defects; re-review found three
  remaining Important gaps. All were corrected. Final re-review returned `Ready: Yes` with no
  Critical, Important, or Minor findings.
- Task 6.9 and S6R1 are Accepted as a test contract only. The ledger is 37/80. S6R2 is Ready; Task
  6.10 remains unchecked, later S6R projection/relationship increments remain Specified, and S7
  remains blocked until aggregate S6R acceptance.

## S6R2 catalog/shared-boundary acceptance — 2026-07-13T18:57:32Z

- Added a separate deterministic internal-reference catalog for `person`, `technology_concept`, and
  `technology_route`, bound to exact accepted v1 content/file identities and exact ADR/release-spec
  source hashes/citation ranges. Evidence and packaged bytes have content SHA-256
  `ff347833…45a7` and file SHA-256 `84d77838…dbbf`; historical v1 remains byte-identical at
  `b227285f…c0`.
- Person relationship v2 rows change only target ownership/version binding: predecessor role,
  evidence, time, and eligible-path semantics remain frozen. Technology rows distinguish
  discussion-or-mention, claimed adoption, and demonstrated use, reject unresolved terms as
  canonical endpoints, and explicitly do not entail Product capability.
- Projection and index manifests require explicit scope plus domain/reference ownership under
  `canonical-v2-build-manifest-v2`. The new installed catalog is a separate deep module and the
  compatibility names on `domain_catalog` load lazily, so unchanged v1 consumers keep their former
  import/failure surface.
- Builder/validator TDD moved from ten missing-script/artifact RED failures to `13 passed`, including
  rehashed semantic mutations and symlink-parent write escape. The final catalog/shared suite was
  `32 passed, 5 xfailed`; full no-external-database Canonical V2 was
  `214 passed, 137 skipped, 9 xfailed` with no real failure.
- Deterministic `--write`/`--check`, evidence/package and historical-v1 `cmp`, wheel inclusion of
  both catalogs, Ruff check/format, Pyright, strict OpenSpec, diff, scope, high-confidence secret,
  and generated-cache checks passed.
- Initial main review found three Important defects; the focused integrity audit found three more:
  unresolved Technology policy, eager v1 coupling, incomplete semantic validation, v1 manifest
  byte drift, symlink-parent escape, and unapproved Person role/path/time changes. All six were
  corrected. Both final reviews returned `Ready: Yes` with zero Critical/Important findings.
- Known Minor/YAGNI risk: the two development artifact replacements are sequential, so interruption
  can temporarily break parity; `--check` detects the condition. This slice writes no database,
  index, release pointer, provider, or product state.
- S6R2 is Accepted. Task 6.10 stays unchecked and the ledger stays 37/80. S6R3 Person projection is
  Ready; S7 remains blocked until S6R4 and aggregate S6R acceptance.

## S6R3 Person reference projection acceptance — 2026-07-13T20:37:07Z

- Added a package-internal pure `InternalReferenceProjectionBuilder` for the Person increment. Its
  request carries exact domain-projection and Person-identity request/result pairs; the builder
  deterministically rebuilds the domain result, applies the identity module's exact-result
  validator, and rejects any pair or envelope drift before deriving output.
- Domain and Person assertions remain separate. Every Person reference binds an exact typed public
  root/subobject, domain lineage, shared source record, exact `identity.name`, and a content-bound
  object crosswalk. Same-record/same-name author sources cannot swap object ownership. ORCID uses
  the identity module's version-stable normalization, requires a retained assertion owned by the
  exact Person source, permits that assertion on another validated profile record, and rejects a
  mismatch with typed `PaperAuthor.orcid`.
- Person admission is derived rather than caller-declared. Accepted current verdicts may upgrade
  prior unresolved topology; current unresolved evidence does not silently downgrade accepted
  topology; name-only ambiguity remains explicit unresolved references. Anchors and references are
  1:1, resolved projections retain assignment/topology verdict lineage and shared source records,
  and aliases/display names derive only from references.
- Results are deterministic/content-addressed and expose
  `validate_internal_reference_projection_result(request, result)`. The verifier replays the full
  closed graph and rejects even a completely rehashed fabricated name/result. S7 publication and
  later consumers must use this verifier rather than trusting a standalone output hash.
- Focused Person/reference was `14 passed, 3 expected xfailed`; the domain/identity/import-order
  matrix was `76 passed, 3 expected xfailed`; complete no-external Canonical V2 was
  `229 passed, 137 skipped, 7 expected xfailed`. The three local xfails are exact S6R4 Technology/
  relationship REDs; the other four are the existing future public-module REDs. Ruff check/format,
  Pyright over both changed source files and all three changed test files, strict OpenSpec,
  `git diff --check`, scope, and high-confidence secret checks passed.
- Two final independent read-only reviews returned `Ready: Yes` with zero Critical, Important, or
  Minor findings after closing exact-pair, rehashed-name, anchor-reuse, historical-verdict,
  forged/cross-record ORCID, same-record object-swap, and stale-future-RED/static counterexamples.
- S6R3 is Accepted without persistence, migration, database/index/provider/release writes, or a
  fifth public domain. Task 6.10 and the ledger remain unchecked/37 of 80; S6R4 is Ready, aggregate
  S6R and S7 remain blocked.

## S6R4 Technology/relationship acceptance — 2026-07-13T22:30:44Z

- The inherited S6R1 contract first exposed seven strict RED groups. After S6R3, the three remaining
  Technology/relationship groups were still expected xfails; the final complete Canonical V2 run
  leaves only the four named future public-module xfails, proving the S6R4 groups crossed to GREEN.
- Added a versioned Technology identity method with exact strong/recall keys. Pure TechnologyConcept
  and TechnologyRoute projections retain aliases, definitions, hierarchy, public crosswalks,
  source records, observations, release identity, content hashes, and assertion-level field
  lineage. Sparse unresolved evidence remains a noncanonical reference. Repeated equivalent
  append-only observations, including reordered set-like alias values, remain in lineage.
- Relationship projection now uses an explicit, versioned combined registry while preserving the
  exact legacy 34-type profile. Checked internal Person and Technology endpoints fail closed on
  unresolved, registry, lineage, assertion-to-record, artifact, term, time, semantic-state, or
  typed Professor-path drift. Technology relations preserve separate discussion-or-mention,
  claimed-adoption, and demonstrated-use semantics. They create neither Product capability nor an
  Industry Brief fact and do not widen the four public root domains.
- The PostgreSQL adapter persists and queries exact `(relationship_type_id, version)` pairs, retains
  current/legacy request/result hash profiles, replays raw historical C2_0010 rows, and rejects new
  internal-reference persistence until S7. No migration was needed or changed. On the owned,
  explicitly marked disposable target `canonical_v2_s6r4_base`, the complete relationship adapter
  file returned `19 passed in 22.33s`, including restart/replay, old/new coexistence, concurrency,
  rollback, and safety. Only the unchanged base database remained after the run; the owned container
  `codex-canonical-v2-s6r4-pg` was then stopped and removed.
- Final pure evidence: the six-file focused matrix returned `75 passed, 14 skipped`; all skips were
  explicit real-PostgreSQL tests with no target configured. Complete no-external Canonical V2
  returned `244 passed, 139 skipped, 4 expected xfailed in 12.15s`. The four xfails are exactly the
  future KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, and ReleasePublication interfaces.
- Ruff check and format passed for the nine focused source/test files; Pyright reported `0 errors, 0
  warnings, 0 informations`. The deterministic internal-reference catalog `--check`, strict
  OpenSpec, `git diff --check`, migration scope, generated-cache scope, and high-confidence secret
  checks passed. The final code change was internal pure comparison logic, so the already-green,
  unchanged PostgreSQL adapter/test inputs did not require a second disposable run.
- Final independent specification and integrity reviews each returned zero Critical, zero Important,
  and one shared Minor. Persistence review returned zero findings. The accepted nonblocking Minor is
  that the combined registry hash binds source catalog hashes plus adapter metadata rather than a
  direct fingerprint of the final serialized rows; current factory/input validation prevents an
  injection bypass. S6R5 aggregate review retains this as future drift-defense risk rather than
  expanding S6R4 beyond the user-selected non-idealized design.
- S6R4 and Task 6.10 are Accepted. The ledger is 38/80. S6R5 aggregate S6 reacceptance is Ready;
  S7 remains blocked. No original/recovery/durable-candidate database, Milvus index, provider,
  release pointer, commit, push, PR, archive, or cutover was touched.

## S6R5 aggregate S6 reacceptance — 2026-07-14T02:05:34Z

- Aggregate contract accounting proves exactly four public domains, three internal auxiliary
  reference types, six public paths, the preserved 34-row legacy relationship registry, and the
  additive 40-pair combined registry. `product_has_capability`, a fifth public Person/Technology
  domain, and an Industry Brief canonical fact remain absent. Detailed hashes, counts, fixture
  projections, and the Pattern-fix report are in `s6r-aggregate-review.md`.
- The historical v1 catalog remains byte-identical at `b227285f…c0`; its accepted 14-source/four-
  domain snapshot audit is retained rather than rebinding immutable history to moved current
  documentation. The current internal-reference evidence/package pair remains byte-identical at
  `84d77838…dbbf`, validated content `ff347833…45a7`; builder `--check` and 13 validator tests passed.
- The exact identity transition contract closes internal unresolved ownership, method/entity,
  recalled-component verdict, owner/source/input/output/assignment/history, accepted topology,
  reject, split, and reversal continuity bidirectionally. Final identity was `53 passed`; identity
  plus internal reference projection was `79 passed`.
- Final pure aggregate verification was `167 passed`. Complete no-external Canonical V2 was `265
  passed, 139 skipped, 4 expected xfailed`; the four xfails are exactly the future KnowledgeBuild,
  KnowledgeRead, KnowledgeAnswer, and ReleasePublication interfaces.
- The final owned tmpfs PostgreSQL identity/domain/relationship lifecycle matrix was `68 passed in
  73.11s`. It exercised migrations, exact target gates, restart/replay, conflicts, concurrency,
  rollback, and relationship-version coexistence. Only the marked empty base and `postgres`
  remained before cleanup; the base had zero non-system tables, no sibling database remained, and
  the owned container plus loopback port were removed. The unchanged database-integrity matrix had
  already returned `27 passed` at unique head `C2_0010` with 83 non-system tables before its own
  cleanup.
- Ruff check passed; the 17 S6R-owned Python files were formatted; complete Canonical V2 Pyright
  returned zero findings. A fresh wheel contained 266 entries, all seven required S6R package
  entries, and zero `.agents` entries. Nine imports, lazy historical catalog loading, and the unique
  `C2_0010` Alembic head passed.
- Strict OpenSpec, formal S2B `accepted/50`, original-`pgtest` pause, diff, migration-scope,
  generated-cache, high-confidence secret, and import checks passed. Two final independent delta
  re-reviews returned zero Critical, zero Important, and zero Minor findings.
- The earlier aggregate review's direct-final-row registry fingerprint and transactional two-copy
  catalog replacement ideas remain recorded nonblocking Minor/YAGNI hardening. Per explicit user
  direction, S6R5 was not expanded beyond its Required checks and zero-Critical/Important bar.
- S6R5, aggregate S6R, and Task 6.11 are Accepted. The ledger is 39/80. S7 release/index RED is Ready;
  S2C still gates S8/S9 acceptance-oracle execution. No original/recovery/durable-candidate database,
  Milvus index, provider, active pointer, commit, push, PR, archive, or cutover was touched.

## S7A Task 7.1 release-lifecycle RED acceptance — 2026-07-14T02:39:06Z

- Five minimal scenarios freeze the six existing Task 7.1 behaviors through the design-frozen
  `KnowledgeBuild.build` and `ReleasePublication.verify/promote/rollback` methods: isolated failed
  candidate/retry, candidate-manifest binding, immutable deterministic public/auxiliary hashes,
  parity-mismatch refusal with repair evidence, one-release promotion, and auditable rollback.
- Package-internal ephemeral factories are composition seams only. Fixture dependencies supply
  upstream materialized sections, actual index manifests, stores, a clock, and a failure boundary;
  the target modules must produce candidate/manifest hashes, failure receipts, parity decisions,
  pointer transitions, verification records, and publication history. Test-local subclasses do not
  implement target behavior.
- Normal focused RED was exactly `5 xfailed`. Forced RED was exactly five guarded target-module
  failures: three for absent `knowledge_build`, two for absent `release_publication`. Each importer
  checks `ModuleNotFoundError.name`; a nested missing dependency is a real failure rather than an
  accepted xfail.
- Shared manifest/release controls were `16 passed`. Complete no-external Canonical V2 was `265
  passed, 139 skipped, 7 expected xfailed`; the five Task 7.1 xfails plus future KnowledgeRead and
  KnowledgeAnswer are the complete expected set.
- Ruff check/format passed for both S7A owner files; targeted Pyright returned zero findings. Strict
  OpenSpec, `git diff --check`, owner scope, generated-cache scope, and high-confidence secret checks
  passed. No database, index, candidate data, provider, or active pointer was used.
- Initial independent review found two Important false-GREEN/masking gaps; the first re-review found
  one remaining Important intermediate-state gap. Concrete module composition, mutation-sensitive
  hashes, exact missing-target sentinels, and the post-promote/pre-rollback three-pointer assertion
  closed them. Final review returned zero Critical, zero Important, and one nonblocking Minor.
- The Minor is intentionally deferred rather than expanded: Company/Person and one extra-point
  mismatch are representative here; Tasks 7.3/7.4 own the complete public/Person/Technology and
  missing/extra/stale/cross-release matrices.
- S7A and Task 7.1 are Accepted at 40/80. Task 7.2 is Ready. No KnowledgeBuild/ReleasePublication
  implementation, PostgreSQL/Milvus/pointer write, commit, push, PR, archive, or cutover occurred.

## S7B Task 7.2 KnowledgeBuild acceptance — 2026-07-14T06:00:15Z

- `KnowledgeBuild` now exposes only `build(BuildCandidateRequest) -> CandidateRelease`; its
  package-internal composition seam consumes already-materialized typed sections and does not own
  Task 7.3 projection production, Task 7.4/7.5 index construction, or Task 7.6 publication.
- Canonical source-batch identities and parser/policy/model versions, complete decision/object/
  relationship/eligibility sections, public/internal published projections, expected index
  projections, UTC creation time, and the run/release identity are bound by a full canonical-JSON
  manifest self-hash. Candidate and manifest nested version/count maps reject in-place mutation.
- Materialization failure retains its first inspectable/retryable receipt, publishes neither store,
  and re-raises the original error. Fully validated candidates are retained only after construction;
  exact same-ID replays are idempotent and different content cannot overwrite either immutable
  store. The active canonical/published/index mapping is observed but never written.
- Pre-implementation RED was exactly three named xfails and three exact missing-target forced
  failures. Final owner verification was `3 passed`; combined KnowledgeBuild/ReleasePublication was
  `3 passed, 2 expected xfailed`; shared contracts were `16 passed`.
- Complete no-external Canonical V2 was `268 passed, 139 skipped, 4 expected xfailed`. The remaining
  xfails are exactly KnowledgeRead, KnowledgeAnswer, and the two Task 7.6 ReleasePublication cases.
- Focused Ruff check/format and complete Canonical V2 Pyright passed with zero findings. A fresh
  267-entry wheel includes `knowledge_build.py` and no `.agents` entries. Strict OpenSpec,
  `git diff --check`, production-scope, high-confidence secret, and generated-cache checks passed.
- Independent review returned zero Critical, zero Important, zero Minor, and one nonblocking YAGNI:
  a durable adapter may later define a real transaction boundary and typed multi-stage failure
  receipt; Task 7.2 does not require either.
- S7B and Task 7.2 are Accepted at 41/80; Task 7.3 is Ready. No PostgreSQL, Milvus, provider,
  candidate-data, active-pointer, commit, push, PR, archive, publication, or cutover write occurred.

## S7C Task 7.3 candidate projection acceptance — 2026-07-14T06:57:15Z

- The pure package-internal `compose_candidate_projections` function revalidates its request and
  calls the Accepted S6R exact closed-graph replay validator before producing output. It consumes no
  database, index, provider, active-pointer, relationship, or path-eligibility adapter.
- Every result contains typed public-domain, Person, Technology-concept, and Technology-route
  records plus exactly seven `ProjectionManifest` envelopes. The public owner set is exactly
  Company/Paper/Patent/Professor; internal Person/Technology owners remain
  `internal_auxiliary`, including explicit zero-count populations.
- Each owner manifest binds only its release, scope, owner, projection kind/version, and sorted
  record identity/content hashes. A real fixture change from one resolved Technology route to an
  unresolved route preserves all four public hashes while changing the route count/hash and bundle
  hash. Repeated identical composition is byte-identical.
- Resolved Person and Technology records preserve their upstream source-anchor/assertion/decision/
  time lineage. Two same-name unresolved Person references remain upstream diagnostics and produce
  a zero-count Person manifest; no Person, Technology, Product, Industry Brief, or Product-
  capability population widens the four public domains.
- Pre-implementation RED was exactly `4 xfailed`; forced RED was four exact absent-target failures.
  Final focused Task 7.3 was `4 passed`; complete Internal Reference was `28 passed`; combined
  KnowledgeBuild/ReleasePublication was `3 passed, 2 expected xfailed`; shared contracts were `16
  passed`.
- Complete no-external Canonical V2 was `272 passed, 139 skipped, 4 expected xfailed`. The remaining
  xfails are exactly KnowledgeRead, KnowledgeAnswer, and the two Task 7.6 ReleasePublication cases.
- Focused Ruff check/format and complete Canonical V2 Pyright passed with zero findings. A fresh
  268-entry wheel includes both S7B/S7C modules and no `.agents` entry. Strict OpenSpec,
  `git diff --check`, production-scope, high-confidence secret, and generated-cache checks passed.
- Independent review returned Accept with zero Critical, zero Important, and zero Minor. Task
  7.4-7.6 index/lookup/vector/publication work remains correctly deferred YAGNI.
- S7C and Task 7.3 are Accepted at 42/80; Task 7.4 is Ready. No new Release/Milvus acceptance box
  closes until its actual index/lookup owners pass. No database, index, pointer, provider, commit,
  push, PR, archive, publication, or cutover write occurred.

## S7D Task 7.4 index-projection RED acceptance — 2026-07-14T08:11:49Z

- Four minimal strict RED scenarios freeze the Task 7.4 contract without production implementation:
  release/object/content/version metadata and Professor split; evidence-anchored internal
  Technology/no-fifth-domain ownership; derived initial/schema/embedding/eligibility full rebuild;
  and point-level missing/extra/stale/cross-release parity through future ReleasePublication.
- The future package-internal seam is one `IndexProjectionBuilder.build(IndexProjectionRequest) ->
  IndexProjectionResult`. Its request binds the exact S7C request/result and exact replayable public
  PathEligibility request/result pairs. Internal Person/Technology use a separate versioned
  evidence-anchor policy rather than fabricating a fifth public PathEligibility domain.
- The admitted real fixture freezes exactly six points: Company, Paper, Patent, Professor identity,
  Professor research, and internal Person. A real semantic-recall exclusion removes only Paper and
  changes its owner count/entity/content hashes. A second real fixture freezes Company plus two
  Technology concepts/one route while empty owners retain manifests.
- Every point binds canonical object, release, opaque projection join, typed scope/domain/reference/
  Professor view, path, projection/schema/embedding/eligibility versions, exact source-projection
  hash, exact embedded-content hash, and source evidence. Person/Technology points retain accepted
  public evidence anchors; every expected manifest's count/policy agrees with its joined points.
- Point parity uses typed expected/actual inventories, classifies each defect exactly once, persists
  point/projection/object/release/version/content repair evidence, blocks promotion, and leaves all
  active pointers unchanged. Aggregate-only manifest counters are not treated as repair evidence.
- Final normal RED is exactly `4 xfailed`; forced RED is exactly four guarded target-module failures:
  three absent `index_projection` and one absent `release_publication`. The complete owner pair is
  `28 passed, 6 xfailed`; KnowledgeBuild/ReleasePublication is `3 passed, 3 xfailed`; shared
  contracts are `16 passed`.
- Complete no-external Canonical V2 is `272 passed, 139 skipped, 8 expected xfailed`: the three Task
  7.4 index REDs, three ReleasePublication REDs, KnowledgeRead, and KnowledgeAnswer. Ruff check/
  format and complete Canonical V2 Pyright pass with zero findings.
- Strict OpenSpec, `git diff --check`, production-scope, high-confidence secret, generated-cache,
  and package-content gates pass. A fresh 268-entry wheel retains S7B/S7C and includes neither
  `.agents` nor the intentionally absent Task 7.4/7.6 production modules.
- Independent review found five Important false-green gaps across point repair content, exact
  eligible population/Person ownership, eligibility-outcome consumption, Professor manifest split,
  and manifest policy binding. All were repaired; final review is zero Critical, zero Important,
  zero Minor. Two YAGNI notes are nonblocking: do not split the long fixture or freeze physical
  collection/vector-dimension/durable-adapter details in RED.
- S7D and Task 7.4 are Accepted at 43/80; Task 7.5 is Ready. No Release/Milvus acceptance checkbox
  closes, and no production module, database, index, pointer, provider, commit, push, PR, archive,
  publication, or cutover write occurred.

## S7E Task 7.5 index-projection GREEN acceptance — 2026-07-14T10:22:52Z

- `IndexProjectionBuilder.build(IndexProjectionRequest) -> IndexProjectionResult` now exactly
  replays its S7C candidate and each public PathEligibility decision before constructing stable,
  release-independent lookup-document and vector-point identities. It retains empty owner envelopes,
  separates Professor identity/research content, keeps exact lookup independent of semantic
  exclusion, and materializes internal Person/Technology only from accepted evidence anchors.
- Eight vector manifests and seven lookup manifests bind release, object/content, projection/schema,
  embedding, eligibility, evidence, count, and full-rebuild state. Initial/schema/embedding/
  eligibility changes derive a full rebuild rather than trusting the caller's requested mode.
- The package-internal isolated adapter accepts only a fresh absolute marked target, revalidates the
  Accepted S2B gate before target/client preparation and immediately before first write, then writes
  and reads back deterministic recorded embeddings in real Milvus Lite plus lookup documents,
  manifests, and a successful receipt in SQLite. Original, relative, network, unmarked, symlink-
  escaping, and invalid-identity targets fail before client open or write.
- Pre-implementation normal RED was exactly three index-projection xfails; forced RED was exactly
  three absent-module failures. Final owner verification is `40 passed`; owner plus release
  interfaces is `40 passed, 3 xfailed`. The three remaining release-interface xfails belong exactly
  to Task 7.6.
- Complete no-external Canonical V2 is `284 passed, 139 skipped, 5 xfailed`: only KnowledgeRead,
  KnowledgeAnswer, and the three Task 7.6 scenarios remain expected RED. Accepted S2B admission is
  freshly `5 passed`; the retained real-target acceptance run is `1 passed in 12.98s`.
- Complete Canonical V2 Ruff and Pyright pass; focused format passes. A fresh 270-entry wheel at
  `/var/tmp/canonical-v2-s7e-wheel-20260714T101559Z/miroflow_agent-0.1.0-py3-none-any.whl` has SHA-256
  `fa84842d50e4d5980bd63b9a28ce4fcb0a9944126089e8a59a79e0a3f35073a1`, includes both index modules,
  and excludes `.agents`. Strict OpenSpec, imports, diff, source/write-boundary, secret, and generated-
  cache gates pass.
- Content-addressed execution evidence is persisted at
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7e/isolated-index-rebuild-receipt.json`.
  It records six Milvus points, five lookup documents, all 8/7 owner manifests, exact target artifact
  hashes, Accepted S2B hashes, and the absent release-pointer capability. Original Milvus remains
  SHA-256 `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`;
  original `pgtest` remains paused on its exact recorded volume.
- Three independent final reviews report zero Critical and zero Important findings. Receipt-root
  binding, aggregate-manifest limits, illustrative in-memory active-state evidence, durable cleanup,
  production adapters, and fixture splitting remain recorded nonblocking Minor/YAGNI; Task 7.6 keeps
  full point-level reconciliation ownership.
- S7E and Task 7.5 are Accepted at 44/80; Task 7.6 is Ready. No commit, push, PR, publication,
  promotion, rollback, archive, or cutover occurred.

## S7F Task 7.6 release-publication GREEN acceptance — 2026-07-14T11:00:20Z

- The new deep `ReleasePublication` module preserves the frozen `verify`, `promote`, and `rollback`
  interface and shared `ReleaseVerification`/`PublishedRelease` identities. Its only composition seam
  consumes explicit in-memory candidate manifests, expected/actual index manifests and points, the
  three-key snapshot, evidence stores, history, and clock; it has no file, database, Milvus, network,
  environment, alias, or real-pointer capability.
- Verify compares complete expected/actual manifest objects and mutually exclusive point inventories.
  Both inventories independently bind count, exact S7E entity-ID/content hashes, release, scope,
  domain/reference owner, path, projection/schema/embedding/eligibility versions, and point metadata.
  Missing/extra/stale/cross-release point evidence is deterministic and persists complete immutable
  expected/actual snapshots before any promotion decision.
- Promotion is an explicit method call and requires a stored accepted verification bound to the exact
  candidate manifest; every rejected path is a state no-op. The accepted in-process rehearsal updates
  exactly canonical/published/index release keys to one release and appends history. Rollback requires
  that release still be active, restores the promotion's recorded prior three-key snapshot, and
  retains candidate, verification, discrepancy, and history evidence.
- Pre-GREEN normal RED was exactly three xfails and forced RED exactly three absent-target failures.
  The original owner scenarios are GREEN. Review exposed three executable Important gaps—matching
  forged aggregate hashes, lost evidence on actual manifest/count drift, and incomplete stale repair
  details. Three focused RED/GREEN regressions closed them; final owner is `6 passed`.
- `KnowledgeBuild` plus ReleasePublication is `9 passed`; S7E owner plus ReleasePublication is
  `46 passed`; shared contracts are `16 passed`. Complete no-external Canonical V2 is
  `290 passed, 139 skipped, 2 xfailed`, leaving only KnowledgeRead and KnowledgeAnswer expected RED.
- Complete Ruff and Pyright pass; focused format/import pass. The fresh 271-entry wheel at
  `/var/tmp/canonical-v2-s7f-wheel-20260714T105913Z/miroflow_agent-0.1.0-py3-none-any.whl` has SHA-256
  `7f6986509d6b758920483f179e51c0a476774295e3018bd4889856301dab9316`, includes the module, and
  excludes `.agents`. Strict OpenSpec, diff, production-scope, secret, cache, frozen-source, and
  original-target checks pass.
- Final independent re-review is zero Critical and zero Important. A custom failure/concurrency-aware
  mutable-store transaction, durable repositories, production authorization, real pointer adapters,
  and physical DB/index rollback are nonblocking Minor/YAGNI and remain Task 7.7/later ownership.
- S7F and Task 7.6 are Accepted at 45/80; Task 7.7 is Ready. No real publication/promotion/rollback,
  database/index/alias/pointer mutation, commit, push, PR, archive, or cutover occurred.

## S7G Task 7.7 isolated-release rehearsal RED acceptance — 2026-07-14T11:49:32Z

- Exactly three strict integration scenarios freeze the missing package-internal isolated
  publication adapter: full physical lookup/Milvus parity plus real disposable-PostgreSQL pointer
  promotion/rollback; refusal of one receipt-external physical Milvus point with retained repair
  evidence; and fail-closed explicit database/index/release identity before connect, client open, or
  pointer write. The future adapter must reuse S7F `verify/promote/rollback`; no public interface or
  migration is introduced by RED.
- Normal focused execution returned exactly `3 xfailed in 6.68s`. Forced `--runxfail` returned
  exactly three `_MissingIsolatedReleasePublicationModule` failures in `6.69s`, each rooted only in
  absent `src.data_agents.canonical_v2.release_publication_isolated`. Import happens before external
  target setup, so environment skip cannot hide RED.
- S7E owner plus S7F publication returned `46 passed, 3 xfailed`; complete no-external Canonical V2
  returned `290 passed, 139 skipped, 5 xfailed`. The five are exactly S7G's three scenarios and the
  existing KnowledgeRead/KnowledgeAnswer future-interface REDs.
- Complete Ruff check and Canonical V2 Pyright passed; focused format, strict OpenSpec,
  `git diff --check`, scope/secret/cache, absent-production-module, frozen-source, and original-target
  checks passed. Original Milvus remains SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`; original `pgtest` remains
  paused on its recorded volume.
- Two independent read-only reviews bound to test SHA-256
  `111dbaabe230932a31a3b5cd4879a0960611d7babf290604223036ffbc61477a` report zero Critical and zero
  Important findings. Fixture extraction, fixed IDs on the required fresh disposable database, and
  duplicating already-covered physical missing/stale/cross-release variants remain nonblocking
  Minor/YAGNI.
- S7G RED is Accepted at 45/80. Task 7.7 and its rollback acceptance item remain unchecked; S7H
  GREEN is Ready. No production module, external target, database/index/pointer state, migration,
  commit, push, PR, publication, rollback, archive, or cutover changed.

## S7H Task 7.7 / Aggregate S7 acceptance — 2026-07-14T12:46:02Z

- Added a package-internal complete physical audit that validates the marked target, exact two-key
  release/collection metadata, receipt, lookup documents/manifests, every Milvus point JSON/scalar/
  vector, and the target's only collection. Milvus points are enumerated independently of receipt
  IDs, so one unreceipted point reaches S7F reconciliation as exactly one repairable `extra` instead
  of being hidden or raised before evidence persistence.
- Added a package-internal isolated publication adapter over the unchanged S7F
  `ReleasePublication.verify/promote/rollback` interface. It admits only an explicit identity-checked
  `disposable` PostgreSQL target, ignores generic `DATABASE_URL`, validates exact release/build-
  manifest registry continuity, requires prior accepted verification, re-audits the candidate and
  compares its complete snapshot before promotion, and exact-audits the prior target before rollback.
- The three-key active state is a guarded mapping backed by one SQL `UPDATE` transaction that changes
  primary/canonical/published/index release IDs plus predecessor/time together and uses the complete
  prior row as an optimistic condition. Partial key mutation is forbidden; a rejected or drifted
  candidate leaves the prior pointer unchanged.
- On fresh owned network-none/no-port PostgreSQL at existing head `C2_0010`, the existing active-
  pointer mixed-version/transaction invariant passed `1 passed`; the final current-code rehearsal
  passed exactly `3 passed, 40 deselected in 20.45s`. It verified/promoted/read/rolled back two fresh
  physical releases, refused one extra point with retained evidence, and rejected malformed/
  cross-wired targets before connect/client open/pointer write. Final DB state restored all release
  fields to `accepted-s7g-r0`, retained both release/manifests, and kept landing counts `0/0/0`.
- A review found one Important complete-audit gap: SQLite `build_metadata.release_id` was not read.
  Exact two-key metadata/release validation plus a zero-Milvus-open regression closed it. Two final
  independent reviews then reported zero Critical/Important findings.
- Final siblings are S7F `6 passed`, S7E/S7F owner `47 passed, 2 skipped`, KnowledgeBuild plus
  ReleasePublication `9 passed`, and shared contracts `16 passed`. Complete no-external Canonical V2
  is `291 passed, 141 skipped, 2 xfailed`; only KnowledgeRead and KnowledgeAnswer remain RED.
- Complete Ruff/format/Pyright, import, 272-entry wheel, strict OpenSpec, diff/scope/secret/cache,
  frozen-target, and resource-cleanup gates pass. Wheel SHA-256 is
  `aa9471c025dd129fe181e0fbb82823f57f93abb2420794e7736dcf0c4276136a`. The secret-free receipt at
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7h/isolated-release-rehearsal-receipt.json`
  records DB evidence SHA-256
  `f1d775f0dd24aad07500b48330a653f16f57d29c2c8a25978c2f1df263b08e18` and cleaned resource IDs.
- Original Milvus remains SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`; `pgtest` remains paused on
  its exact volume. S7H, Task 7.7, and aggregate S7 are Accepted at 46/80. S2C is the next prerequisite
  before S8/S9 acceptance-oracle execution. No Commit, Push, PR, production promotion, archive, or
  Cutover occurred.

## S2C1 claim-level case-contract RED acceptance — 2026-07-14T15:46:46Z

- Added exactly six strict-xfail test groups under the run-local S2C boundary. They freeze strict
  schema/version/content identity, atomic claim/entity/variant constraints, replayable snapshot/
  as-of/enumeration coverage, observable stage oracles, closed per-case hard outcomes, and
  reference prose as review-only context.
- Normal focused RED returned exactly `6 xfailed in 0.11s`. Forced `--runxfail` returned exactly
  `6 failed in 0.11s`, all `_MissingClaimLevelCaseContractModule` for the exact absent future
  `claim_level_case_contract.py`; there were no skips, nested dependency failures, or fixture masks.
- Ruff check/format passed and Pyright reported zero findings. Strict OpenSpec and
  `git diff --check` passed; the production tree and historical S2 artifacts were not modified.
- Historical challenge, regression, manifest, and threshold SHA-256 values remain
  `ee46c677...f9f`, `f2656e8c...97da`, `dc7cc10b...088`, and `bce20bf9...b5cc` respectively.
- The initial review found two Important omissions: explicit version/required-field negatives and
  a closed atomic hard-ID set. Both were corrected. Final review bound to test SHA-256
  `8253c84efe0e86a1dad15afb8097f1b3577dc720c4e35fe86894af33991d0b0a` reports zero Critical,
  zero Important, and zero Minor findings.
- S2C1 is Accepted. Task 2.7 stays unchecked and the ledger stays 46/80; S2C2 owns the validator and
  corpus migration, while S2C3 owns judging/human review and aggregate acceptance. No runtime,
  database/index/provider state, Commit, Push, PR, archive, or Cutover changed.

## S2C2 Task 2.7 claim-level corpus migration acceptance — 2026-07-14T16:53:22Z

- Implemented one strict run-local Pydantic contract/validator with exact schema/contract versions,
  canonical content hashes, recursively forbidden extras, deep immutable JSON, stable dump/revalidate
  identity, global ID/reference closure, and a closed per-case hard atomic set. Stale `model_copy`,
  nested mutation, semantic required/forbidden contradiction, entity/type cross-wire, vacuous
  acceptance, and pending claim-evidence acceptance all fail closed.
- Deterministic conversion emits exactly 52 contracts and 53 retained snapshots from the exact 40
  regression plus 12 challenge inputs. Every source ID and family has one accounting row: 29 are
  `pending_user_review`, 23 workbook fact cases are `blocked_missing_evidence`, and zero are
  `human_reviewed` or `acceptance_eligible`. Reference prose/key points remain `review_only`; no
  prose fact or S2C1 synthetic founder/Product claim becomes normative truth.
- Safety case `wb-r009` is a non-enumeration `safety_guidance` case with Web=false, retained exact
  OpenSpec bytes, required lawful guidance, atomic location/business/category allegation,
  discovery/evasion, and unrelated-lifestyle prohibitions, plus bounded official-resource variants.
  The two reviewed near-name cases require the selected target and forbid the near-name Company.
  Named open-world Paper and structured Company list cases use `representative` enumeration.
- Builder `--write` and byte-for-byte `--check` agree on manifest content SHA-256
  `df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff`.
  Corpus/accounting/snapshot/manifest file hashes are `75ff02e0...6668`, `e953c2fc...bc48`,
  `85c1e4c1...e253`, and `fbc95a25...682f` respectively.
- Final focused verification is `11 passed in 0.90s`; historical S2 is `20 passed in 0.27s`. Ruff
  check/format, Pyright with zero findings, strict OpenSpec, `git diff --check`, frozen source hashes,
  scope/secret/cache checks, and deterministic rebuild all pass.
- Two independent final reviews report zero Critical/Important findings. Retained snapshot replay,
  enumeration mapping, safety obligations/variants, deep immutability/round-trip identity, stale-
  instance validation, acceptance eligibility, and entity reference findings were closed. Cross-case
  checking in the artifact validator and unset numeric coverage on pending representative cases are
  recorded Minor/YAGNI and nonblocking.
- Task 2.7/S2C2 is Accepted at 47/80. S2C3/Task 2.8 exclusively owns human review, judge calibration,
  eligible-corpus selection, aggregate S2C acceptance, and S8/S9 unlock. No runtime/provider/
  database/index state, Commit, Push, PR, archive, or Cutover changed.

## S2C3A claim-level oracle RED acceptance — 2026-07-14T17:36:19Z

- Accepted the exact five-group run-local RED contract without changing Task 2.8 or the 47/80
  ledger. Normal execution is `5 xfailed`; forced `--runxfail` is exactly five direct
  `_MissingClaimLevelOracleEvaluationModule` failures for the absent
  `s2c/claim_level_oracle_evaluation.py` target. Combined S2C is `11 passed, 5 xfailed`; historical
  S2 is `20 passed`.
- The RED freezes evaluator-derived atomic required/forbidden claim/entity outcomes, protected slots,
  evidence support, false-exhaustiveness, session transitions, stage localization, hard-case closure,
  and soft-score non-masking. Caller-supplied hard outcomes, private call order, and judge-routing
  flags cannot select acceptance semantics.
- Admission refuses byte drift across all four artifacts and a coherently rehashed accounting-to-
  contract cross-wire before judge invocation. Recorded-fake judge requests bind exact contract,
  `as_of`, structured requirement/observation, and the complete named snapshot while excluding
  reference prose/key points and unrelated snapshots; response identities are canonical hashes.
  Invalid identity, memory, extra-field, snapshot, or timeout decisions make only the exact judged
  requirement unresolved while retaining the complete deterministic outcome projection.
- The single-case synthetic fixture proves only gate reachability. It requires exact human review,
  hard-ID/snapshot/family binding, per-family judge calibration, complete eligible-case accounting,
  and an acceptance record binding artifact, review, calibration, hard-outcome, reviewer-state, and
  exclusion identities. Agent/model review and absent, cross-wired, under-sampled, low-agreement, or
  silently omitted inputs fail closed. Mixed non-empty exclusion evidence remains S2C3C ownership.
- Deterministic builder `--check` preserves 52 contracts/53 snapshots and the Accepted S2C2 corpus,
  accounting, snapshot, and manifest file hashes. Ruff format/check, targeted Pyright with zero
  findings, strict OpenSpec, `git diff --check`, absent-target, source/scope/secret/cache gates pass.
  Two targeted final independent reviews returned `0 Critical / 0 Important / 0 Minor`.
- Final pre-evidence test SHA-256 is
  `185e39e5770b51733cf6deece435e5f49d7827ff6cc521eef4aa8aaa4f4ff0ca`; pre-acceptance Slice
  Contract SHA-256 is `a765d98871572cdaf131fae11a5367f65770d0a27988cabb72fdf5dbcd59c58b`.
  No runtime/provider/database/index/source state, Commit, Push, PR, archive, or Cutover changed.

## S2C3B claim-level oracle GREEN acceptance — 2026-07-14T18:27:07Z

- Implemented the one run-local `evaluate_oracle_run(...)` seam and kept every other model/helper
  private. The final implementation/test SHA-256 values are
  `63c33ef3832855a6a02bf0cc03d1036e7c919c5c4fdd4bf166328b7822e626fd` and
  `0235c3306412acd96aad28177fb4f52745486b831f213a4b57707bbdec9cc3e9`.
- Exact owner GREEN is `5 passed`; combined S2C is `16 passed`; historical S2 is `20 passed`.
  A bounded target-absence recovery check restored exact `5 xfailed` and five forced direct missing-
  target failures, then restored the target byte-identically. The five markers are now conditional
  only on target absence; all test assertions and strict sentinel behavior are unchanged.
- Artifact admission validates deterministic manifest/JSONL bytes, schema/version/content/file/
  output/record identities, exact contract validation, and contract/account/snapshot/source-corpus/
  review/family/eligibility cross-references before any judge request. Coherently rehashed sibling
  cross-wires fail closed.
- Atomic outcomes preserve contract order and canonical JSON type identity, honor allowed variants,
  detect forbidden semantics independent of caller claim/evidence IDs, localize every atomic/stage/
  enumeration outcome, preserve deterministic results on judge failure, and never use soft metrics
  to mask a hard non-pass.
- Recorded judge request/response identities are exact and evidence-bounded. Malformed, mutated,
  unbound, memory-bearing, or failed responses become unresolved. No reference context/prose, live
  provider, network, write, database, or index seam exists.
- Results and acceptance records are deeply immutable and content-addressed. Only an exact one-case
  synthetic fixture can prove human/calibration-gate reachability; non-synthetic/multi-case inputs
  cannot become ready in S2C3B. S2C3C retains real provenance, mixed exclusions, and aggregate
  acceptance ownership.
- Deterministic builder `--check`, Ruff format/check, targeted Pyright with zero findings, strict
  OpenSpec, `git diff --check`, source-hash, focused secret, and cache gates pass. Two final reviews
  bound to the exact SHAs returned zero Critical/Important; the implementation/spec review had zero
  Minor, and the safety review recorded three nonblocking Minor/YAGNI notes: real human provenance
  remains process-owned by S2C3C; first-failure display follows hard-ID order while complete stage
  results remain available; calibration agreement is not capped above `1.0`.
- S2C3B is Accepted without checking Task 2.8 or changing 47/80. Accepted S2C2 artifacts and all
  external state remain unchanged; no Commit, Push, PR, archive, or Cutover occurred.

## S2C3C1 deterministic human-review packet acceptance — 2026-07-14T18:48:51Z

- Accepted only the external-review preparation Slice. Initial RED was `1 xfailed`; forced RED was
  one direct absent-builder sentinel. Final focused packet verification is `1 passed`; combined S2C
  plus packet is `17 passed`; historical S2 remains `20 passed`.
- The builder invokes only the public S2C3B admission seam with the fixed Accepted manifest content
  SHA, captures manifest plus all three output bytes after admission, checks their hashes against the
  returned artifact identity, and parses only those same captured bytes. The closed TOCTOU finding
  cannot attach unadmitted case/account bytes to an admitted identity.
- Packet content self-hash is
  `d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb`; builder/test/packet file
  SHA-256 values are `6aa0007b...8272`, `c9939066...b2f4`, and `22277721...7d2e`.
- Exactly 52 cases are accounted once: 29 pending-review templates, 23 blocked evidence-gap
  exclusion candidates, and 18 family calibration templates. No decision is approved; reviewer,
  agreement, sample, and model identity remain null/empty, with model selection explicitly pending
  external authorization. Reference prose/key points are absent; only review-only locator/hashes
  remain.
- Deterministic write/check, Ruff format/check, targeted Pyright with zero findings, strict OpenSpec,
  diff/source/secret/cache gates pass. Independent final review returned zero Critical/Important/
  Minor and Accepted only S2C3C1.
- S2C3C2 is Ready but requires attributable external human decisions, a second human for calibration,
  an authorized real judge model identity, measured family calibration, and explicit decisions on
  every exclusion proposal. Task 2.8/S2C/S8/S9 remain open at 47/80. No external state, Commit, Push,
  PR, archive, or Cutover changed.

## S10A Task 10.1 knowledge-gap trigger RED acceptance — 2026-07-14T19:23:58Z

- Accepted one test-only deep-module RED contract around
  `KnowledgeGapFeedback.record(GapSignal) -> KnowledgeGap`. Three strict groups account for all
  eight Task 10.1 triggers: no result, insufficient evidence, repeated current-Web dependence,
  recurring answer-scoped Product-capability demand, missing relationship, user feedback,
  benchmark failure, and index parity.
- Synthetic signals bind release, affected domains/paths, symptom, available evidence, and at least
  one query/answer/benchmark/telemetry trace. The caller cannot submit final gap identity,
  classification/confidence, review/lifecycle, demand/PRD-impact accounting, severity, owner/
  remediation, timestamps, or resolution evidence. Repeated/recurring demand derives counts from
  raw observation IDs and produces a nonempty trigger-relevant scenario family.
- The Product case names `delivery-robot-x1`, capability
  `autonomous_elevator_button_operation`, its answer trace, Product identity evidence, Company-only
  general capability evidence, and the missing direct binding. Its only accepted proposal is
  `collect_direct_product_capability_evidence`; the gap remains open/unreviewed and cannot become a
  canonical Product-capability relation.
- Final exact RED evidence is `3 xfailed`; forced `--runxfail` is exactly three
  `_MissingKnowledgeGapFeedbackModule` failures for the absent target. Shared contract plus RED is
  `16 passed, 3 xfailed`; complete no-external Canonical V2 is `291 passed, 141 skipped, 5 xfailed`,
  with only KnowledgeRead, KnowledgeAnswer, and these three named S10A future-interface xfails.
- Complete Canonical V2 Ruff rule checking passed; the changed test passed Ruff format checking;
  complete Canonical V2 Pyright returned zero findings. Strict OpenSpec, `git diff --check`,
  scope/secret/cache, and fresh wheel checks passed. Candidate contract/test SHA-256 values are
  `aebb3a71...a1c4` and `9b8dd6e0...d4b7`; wheel SHA-256 is `aa9471c0...136a` and contains no S10
  implementation/test/evidence artifact.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery lab remains
  network-none/no-port; original Milvus hash-only check remains `43ef203e...67cc`. No database,
  index, source, provider, runtime, or release pointer was touched.
- Independent review closed three Important false-green classes: caller-owned module outcomes,
  Product-capability canonical-remediation ambiguity, and repeated/recurring demand/PRD-impact
  collapse. Final review reports zero Critical/Important and one nonblocking construction-helper
  YAGNI. Task 10.1/S10A is Accepted at 48/80; Task 10.2 and aggregate S10 remain open. No Commit,
  Push, PR, archive, or Cutover occurred.

## S10B Task 10.2 knowledge-gap feedback GREEN acceptance — 2026-07-15T02:10:55Z

- Added one storage/provider-independent deep module,
  `KnowledgeGapFeedback.record(GapSignal) -> KnowledgeGap`. `GapSignal` accepts only normalized
  observation facts and rejects caller-owned identity, classification, priority, lifecycle, time,
  owner/remediation, and resolution outcomes.
- Complete classifier input binds signal/release/domain/path/trace/symptom/evidence/raw-demand/time,
  module-owned demand count, trigger family, and policy version. Same signals produce stable gap IDs;
  one changed field changes request/gap hashes; stale-digest reconstruction is rejected.
- Optional recorded classification is schema-validated and binding-checked. Wrong binding, invalid
  schema, timeout, and connection failure degrade to the deterministic unreviewed proposal;
  `AssertionError`/other implementation defects propagate. Same-class unvalidated Pydantic instances
  are converted to primitive mappings and revalidated before use.
- Repeated-Web, Product-capability, missing-relationship, and index-parity triggers remain
  deterministic under a hostile valid proposal. Product-capability output exclusively proposes
  `collect_direct_product_capability_evidence`; no canonical/Milvus/runtime write path exists.
- Exact RED before implementation was `5 xfailed`; forced RED was five exact missing-target
  sentinel failures. Final focused owner is `5 passed`; shared plus owner is `21 passed`; complete
  no-external Canonical V2 is `296 passed, 141 skipped, 2 xfailed`, only KnowledgeRead/KnowledgeAnswer.
- Ruff rule/changed-file format and complete Canonical V2 Pyright pass. Strict OpenSpec, diff/scope/
  secret/cache, source invariants, and wheel content pass. Candidate contract/module/S10A-GREEN/
  S10B-test hashes are `850bb167...0b9b`, `18d06249...1302`, `661cd849...a29`, and
  `27b13824...f11`; final wheel hash is `af7332f6...4d00`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery lab remains
  network-none/no-port; original Milvus hash-only check remains `43ef203e...67cc`.
- Two independent final reviews report zero Critical/Important. Nonblocking Minor/YAGNI: synthetic
  trigger-level scenario families await Task 10.4/aggregate operational mapping; protected triggers
  still pay classifier cost before discarding proposals; proposal rationale affects gap identity but
  durable dedup/update is outside S10B.
- Task 10.2/S10B is Accepted at 49/80. Tasks 10.3-10.5 and aggregate S10 remain open. No database,
  index, provider, source, release pointer, Commit, Push, PR, archive, or Cutover occurred.

## S9A Task 9.3 evidence-based assessment RED acceptance — 2026-07-15T02:32:31Z

- Accepted one test-only RED contract through the single future
  `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` seam. Three strict groups cover technical
  strength, competitiveness, maturity, and expert standing; explicit user criteria override an
  extra model-selected dimension, while absent criteria permit a small different dimension set per
  question/evidence turn rather than a global registry.
- Every returned supported/conflicting dimension binds only current EvidenceSet IDs. Unknown model-
  memory evidence is removed and the affected explicit criterion becomes `insufficient_evidence`
  with uncertainty rather than poor performance. The overall frame is conditional answer-scoped
  synthesis, with no required fixed/universal weighting, numeric score, or canonical label.
- Final focused normal execution is exactly `3 xfailed`; forced `--runxfail` is three exact
  `_MissingKnowledgeAnswerModule` failures. Complete no-external Canonical V2 is `296 passed, 141
  skipped, 5 xfailed`, exactly KnowledgeRead, the existing S3A KnowledgeAnswer interface, and the
  three S9A assessment groups.
- Complete Canonical V2 Ruff/Pyright, changed-file format, strict OpenSpec, diff/scope/secret/cache,
  and fresh wheel checks pass. Candidate contract/test SHA-256 values are `1378e7d9...1e80` and
  `33f80279...fd34c`; wheel SHA-256 remains `af7332f6...4d00` and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery lab remains network-
  none/no-port; original Milvus hash remains `43ef203e...67cc`. No provider, database, index,
  release pointer, source, or production code was touched.
- Independent review closed conflict-disclosure and supported-outcome false-green findings. Final
  counts are zero Critical/Important. Nonblocking Minor/YAGNI: generic `weights` absence is broader
  than the fixed/universal-weighting requirement, and `canonical is False` is redundant negative
  shape evidence.
- Task 9.3/S9A is Accepted at 50/80. Tasks 9.1-9.2 and 9.4-9.8 remain open; S2C3C2/S2C3C3 still gate
  claim-level S8/S9 acceptance-oracle execution only. No Commit, Push, PR, archive, or Cutover
  occurred.

## S8W Task 8.4 Universal Web RED acceptance — 2026-07-15T02:55:04Z

- Accepted one test-only RED contract through the single future
  `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` seam. A/B/C/D/E/G information plans
  explicitly omit and disable Web, but a server-owned policy must still execute a bounded Web lane
  after usable exact local evidence and return distinct local/current-Web evidence plus trace.
- Ordinary refusal, blocking clarification, interface control, and default safety guidance use a
  fail-on-call Web adapter and return no Web trace/unavailability limitation. Explicit current-
  official safety lookup is one-call/three-result/official-only, filters a nonofficial result, and
  accepts only official evidence bound to a content-addressed snapshot ID/hash, retrieval time, and
  positive byte length; a missing-snapshot official result becomes invalid/unavailable.
- Timeout, connection, and schema-invalid provider outcomes retain exact usable local evidence,
  return no current-Web evidence or succeeded-Web trace, record the exact unavailable failure kind,
  and expose one material freshness limitation.
- Final focused normal execution is exactly `3 xfailed`; forced `--runxfail` is three exact
  `_MissingKnowledgeReadModule` failures. Complete no-external Canonical V2 is `296 passed, 141
  skipped, 8 xfailed`, exactly the existing KnowledgeRead, KnowledgeAnswer/S9A, and three S8W groups.
- Complete Canonical V2 Ruff/Pyright, changed-file format, strict OpenSpec, diff/scope/secret/cache,
  and fresh wheel checks pass. Candidate contract/test SHA-256 values are `5c255b07...9a22` and
  `f6e0e75e...cdb7`; wheel SHA-256 remains `af7332f6...4d00` and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery lab remains network-
  none/no-port; original Milvus hash remains `43ef203e...67cc`. No provider, database, index,
  release pointer, source, or production code was touched.
- Pre-review closed server-policy opt-out, official snapshot grounding, request-count/order, and
  freshness-limitation false-green findings. Both targeted re-reviews end zero Critical/Important.
  Nonblocking YAGNI: S3A-compatible `web_required` and the structured policy mode remain redundant
  inputs pending Task 8.2/8.3 plan consolidation.
- Task 8.4/S8W is Accepted at 51/80. Tasks 8.1-8.3 and 8.5-8.8 remain open; Task 8.1 and claim-level
  S8/S9 acceptance-oracle execution still await S2C. No Commit, Push, PR, archive, or Cutover
  occurred.

## S8S Task 8.6 sufficiency/retry RED acceptance — 2026-07-15T03:28:45Z

- Accepted one test-only RED contract through the single future
  `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` seam. Three strict groups freeze material-
  part supported/conflicting/missing sufficiency, all three enumeration modes, and targeted bounded
  supplemental retrieval without introducing a second public service or a test-local read module.
- Named Product capability is answer-scoped/noncanonical and supported only by evidence bound to the
  same Product, capability predicate, requested capability value, source nature, and observation
  time. Company, other-Product, Technology, same-Product/wrong-capability, and model-memory evidence
  remain negative cases.
- Enumeration coverage content-binds scope/as-of and ID/count-consistent checked/eligible/retrieved/
  displayed/omitted/unknown accounting. Only one fully accounted finite universe may be exhaustive;
  required members each have one included-with-exact-evidence or unsupported-with-reason outcome.
- Supplemental retrieval records exactly one real boundary request per scenario for only unresolved
  conflicting/missing parts. Independent wall-time/provider-call/retry/cost axes stop with exact
  usage/limit receipt, aligned trace, retained initial evidence, limitation, and typed continuation;
  supported parts are never targeted.
- Final focused normal execution is exactly `3 xfailed`; forced `--runxfail` is three exact
  `_MissingKnowledgeReadModule` failures. Complete no-external Canonical V2 is `296 passed, 141
  skipped, 11 xfailed`, exactly the existing KnowledgeRead, KnowledgeAnswer/S9A, S8W, and three S8S
  groups.
- Complete Canonical V2 Ruff/Pyright and applicable dirty-file format checks pass. Strict OpenSpec,
  `git diff --check`, scope/secret/cache, and fresh wheel checks pass. Candidate contract/test
  SHA-256 values are `f1ef5064...f2c5` and `4bbb8298...3bdf`; wheel SHA-256 remains
  `af7332f6...4d00`, contains Accepted `knowledge_gap_feedback.py`, and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery lab remains network-
  none/no-port; original Milvus remains `43ef203e...67cc`. No provider, database, index, release
  pointer, source, or production code was touched.
- Pre-review and targeted re-review closed capability-value, required-member evidence, actual
  supplemental-call, conflict eligibility, false-exhaustiveness, full-accounting, four-axis budget,
  and retained-evidence false-green gaps. Final candidate identity review reports zero Critical/
  Important. No additional Minor/YAGNI finding blocks the deliberately test-only contract.
- Task 8.6/S8S is Accepted at 52/80. Tasks 8.1-8.3, 8.5, and 8.7-8.8 remain open; S2C3C2/S2C3C3
  still gate only Task 8.1 reviewed calibration and S8/S9 claim-level acceptance-oracle execution.
  No Commit, Push, PR, archive, or Cutover occurred.

## S9M Task 9.5 multi-turn RED acceptance — 2026-07-15T04:19:34Z

- Accepted one synthetic test-only RED contract through the single future
  `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` seam. Four strict groups freeze Canonical
  anchor/displayed-set behavior, unresolved Web-handle behavior, ambiguity/clarification selection,
  all conditional continuation reasons, and explicit topic-switch active-state replacement.
- Canonical follow-up binds the exact ordered prior result-set ID and its `representative`/
  `open_world` coverage, retains protected constraints, and uses registered
  `professor_attributed_to_paper` forward/inverse traversal. Hidden evidence/proposal entries occur
  first, so naive truncation cannot exclude them without reading the prior displayed set.
- Mixed Canonical/Web display order, Web snapshot/resolution lineage, ordinal coreference, and
  unresolved traversal refusal remain typed. Hostile proposals cannot turn a Web handle/URL into a
  Canonical ID or produce canonical target claims.
- Non-blocking ambiguity provides an interpretation and switch; blocking ambiguity suppresses
  hostile primary claims/text and returns clarification only. Opaque selections with hostile
  proposals bind exact stored Canonical/Web options and retain decision/snapshot lineage.
- Six continuation triggers, unavailable-option filtering before the three-option cap, exact
  candidate/handle-or-result-set/constraint/evidence/operation/relation binding, stored selection,
  and an independent complete-simple no-offer negative are executable. Explicit topic switch keeps
  only new active state.
- Final focused normal execution is exactly `4 xfailed`; forced `--runxfail` is four exact
  `_MissingKnowledgeAnswerModule` failures. Complete no-external Canonical V2 is `296 passed, 141
  skipped, 15 xfailed`, exactly the existing KnowledgeRead, KnowledgeAnswer/S9A, S8W, S8S, and four
  S9M groups.
- Complete Canonical V2 Ruff/Pyright and changed-test format checks pass. Strict OpenSpec,
  `git diff --check`, scope/secret/cache, and package checks pass. The first isolated wheel attempt
  hit an external mirror TLS failure; a locked offline build succeeded with unchanged SHA-256
  `af7332f6...4d00` and no tests/`.agents` or S9M production module. Candidate contract/test hashes
  are `d3f3e1fe...bcfd` and `441b6e54...1f8f`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port; original Milvus remains `43ef203e...67cc`. Two review tracks plus Candidate identity
  review end zero Critical/Important. Nonblocking Minor/YAGNI: stale local variable labels,
  Task-9.6-owned cross-release misuse, and no separate first-traversal receipt assertion.
- Task 9.5/S9M is Accepted at 53/80. Tasks 9.1-9.2 and 9.4/9.6-9.8 remain open; S2C3C2/S2C3C3
  still gate only claim-level S8/S9 acceptance-oracle execution. No production code, provider,
  database, index, source, release pointer, Commit, Push, PR, archive, or Cutover changed.

## S9G Task 9.1 grounded-answer RED acceptance — 2026-07-15T04:58:03Z

- Accepted one synthetic test-only RED contract through the single future
  `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` seam. Four strict groups freeze material claim/
  evidence/citation closure, direct named-Product capability/status, derived Industry Brief route/
  representative-coverage semantics, and deterministic grounded fallback after prose timeout.
- General claims retain exact expected subject/predicate/value/status/outcome/evidence tuples and
  exact local/current-Web citation provenance. Orthogonal subject/predicate/value traps prevent
  claim/map co-drift; material conflict cannot collapse silently; model memory cannot become
  provenance; a bounded maturity conclusion remains uncertain answer-scoped noncanonical inference.
- Product binding traps independently cover Company, other Product, wrong capability, Technology,
  model memory, and direct-evidence commercial-status promotion. The unsupported result has one
  explicit empty-evidence mapping and zero citations; the supported result retains only direct
  same-Product/exact-capability demonstrated evidence. Both full results forbid canonical Product-
  capability propagation.
- Industry output retains exact route definitions plus discussion, claimed-adoption, demonstrated-
  use, and conflicting semantics for four displayed Companies. TurnResult mirrors the derived brief
  for claims/maps/citations/conflicts/representative coverage and exposes the same open-world
  limitation; hidden, semantic-promotion, and unsupported-Product proposals cannot survive anywhere
  in the serialized result.
- Prose timeout returns an exact one-claim/one-map/one-citation deterministic fallback with supplied
  coverage and typed timeout limitation across independent ephemeral instances, excluding the
  poisoned raw draft and all extra facts.
- Final focused normal execution is exactly `4 xfailed`; forced `--runxfail` is four exact
  `_MissingKnowledgeAnswerModule` failures. Complete no-external Canonical V2 is `296 passed, 141
  skipped, 19 xfailed`, exactly the existing KnowledgeRead, KnowledgeAnswer/S9A/S9M, S8W/S8S, and
  four S9G groups.
- Complete Canonical V2 Ruff check/Pyright and changed-test format checks pass. Strict OpenSpec,
  `git diff --check`, scope/secret/cache, and package checks pass. The whole-directory format
  inventory reports only two unchanged historical S3A interface RED files. A fresh locked offline
  wheel retains SHA-256 `af7332f6...4d00`, includes Accepted `knowledge_gap_feedback.py`, and excludes
  tests/`.agents` and any S9G production module. Candidate contract/test hashes are
  `789df77a...aae0e` and `1836f8b4...e5df9`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. Two independent review tracks end
  zero Critical/Important after closing semantic-binding/status masking, negative/top-level leakage,
  exact retained-claim semantics, and top-level Industry coverage/limitation gaps. Nonblocking
  Minor: fallback SHA identity is compared across runs but not separately content-bound.
- Task 9.1/S9G is Accepted at 54/80. Task 9.2 and Tasks 9.4/9.6-9.8 remain open; S2C3C2/S2C3C3
  still gate only claim-level S8/S9 acceptance-oracle execution. No production code, provider,
  database, index, source, release pointer, Commit, Push, PR, archive, or Cutover changed.

## S10C Task 10.3 gap-remediation RED predecessor acceptance — 2026-07-15T05:35:23Z

- Accepted one synthetic fixture-only RED predecessor through an extension of the existing deep
  module seam, `KnowledgeGapFeedback.apply_remediation(GapRemediationRequest) ->
  GapRemediationResult`. Task 10.3 stays unchecked and the task ledger stays 54/80.
- Three strict groups freeze: reviewed offline relationship-repair linkage while the exact gap
  remains active-unresolved; closure only after the exact candidate release, accepted exact-parity
  verification, and later accepted intended-effect verification; and fail-closed hostile cross-wire,
  stale/tamper, duplicate, caller-final-gap, incomplete-lifecycle, and online-only inputs.
- The active-link result preserves original gap facts and binds exact release/trace/scope/offline-
  run/source-batch/landing/build/candidate lineage. The resolved result adds only accepted review,
  resolving release, verification/effect lineage, transition receipt, and a later update time. Bare
  labels, candidate-only or release-only evidence, Web/model output, and unrelated verifications
  cannot close a gap.
- Content identities bind nested receipts and the outer request/result. Same input is stable;
  changed input separates; caller extras are rejected; constructed Pydantic instances are
  revalidated; the original immutable gap remains unchanged after every rejection. The tests avoid
  freezing a universal remediation-kind matrix or transition-ID encoding.
- Final focused normal execution is exactly `3 xfailed`; forced `--runxfail` is three exact
  `_MissingKnowledgeGapRemediationContract` failures for the absent Task 10.3 surface. Accepted
  S10A/S10B, shared lifecycle, KnowledgeBuild, and ReleasePublication owner regressions are `15
  passed`. Complete no-external Canonical V2 is `296 passed, 141 skipped, 22 xfailed` with no real
  failures.
- Targeted Ruff check/format and Canonical V2 Pyright pass. Strict OpenSpec, `git diff --check`,
  scope/secret/cache, and package checks pass. The locked offline wheel retains SHA-256
  `af7332f6...4d00`, contains 273 entries and Accepted `knowledge_gap_feedback.py`, and excludes
  tests/`.agents` and any S10C production module. Candidate contract/test hashes are
  `9eb04505...ac0d` and `21baad02...0d3f`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. Specification and test-integrity
  final reviews each end zero Critical/Important. Nonblocking YAGNI: do not expand a universal
  remediation-kind compatibility matrix and do not freeze transition-ID encoding.
- S10C RED is Accepted only as Task 10.3's predecessor. Task 10.3 GREEN still requires its own Ready
  contract and accepted operational inputs; Tasks 10.4-10.5 and aggregate S10 remain open. No S2C
  oracle, production/shared code, provider, database, index, source, release pointer, Commit, Push,
  PR, archive, or Cutover changed.

## S8Q1 Task 8.1 fixture query-planning RED predecessor acceptance — 2026-07-15T06:16:26Z

- Accepted one synthetic fixture-only RED predecessor through package-internal
  `create_ephemeral_query_planner(...).plan(QueryPlanningRequest) -> RetrievalPlan`. It remains
  future-hidden by `KnowledgeAnswer`, adds no sixth public module or `KnowledgeRead.plan`, does not
  check Task 8.1, and leaves the ledger at 54/80.
- Four strict groups freeze A-G/safety/enumeration planning, deterministic protected slots and
  displayed-set rewrites plus the full injected institution matrix, ambiguity mechanics under
  mandatory synthetic policies, and internal Person/Technology plan semantics. The same A class
  admits different typed lane/domain plans, so taxonomy is not frozen as one handler switch.
- Ordinary refusal, default safety guidance, blocking clarification, and interface control generate
  no general-Web plan. Explicit current official safety lookup is bounded `official_only` and cannot
  plan venue/district/business discovery. Enumeration requires exact finite-universe or required-
  member evidence; open world remains representative.
- Exact ID/name/year/geography/negation/direction/displayed-set slots survive original/contextual/
  alias/semantic/domain/relationship/Web views. The release/catalog-driven institution matrix binds
  exact raw spans, candidate IDs/names, pure topics, lane filters, aliases, and catalog identity for
  full/alias/multi/ambiguous/unknown/absent/repeated/overlap cases; an injected new alias works
  without a code-specific name list.
- Two independent synthetic ambiguity policies plus a same-request/candidate margin-only flip prove
  the module must consume injected evidence-count/confidence/margin values. Candidate evidence,
  constraints, eligibility, discriminators, qualifying sets, lead math, policy/candidate manifests,
  and proposal identity remain traced; no real calibrated default is frozen or inferred.
- Resolved Person education/Company-role/geography filters bind exact originating public evidence.
  Resolved-nonmatching and unresolved references remain separately traceable and cannot satisfy
  identity-dependent filters/traversal. Exactly two requested accepted Technology routes bind
  definitions and distinct discussion/claimed/demonstrated semantics; a third accepted route stays
  unqueried and an unknown term remains a search view/gap. Person/Technology stay auxiliary and no
  Product-capability relation is planned.
- Raw recorded hostile proposals independently reject lost slots, invented paths, wrong supported-
  path direction, unsupported operations, excessive budgets, request/catalog/release/reference
  cross-wires, public internal-reference promotion, Product capability, and false exhaustiveness.
  Same input is stable; request-only, proposal-only, and policy-only changes separate content
  identities.
- Final focused normal execution is exactly `4 xfailed`; forced `--runxfail` is four exact
  `_MissingKnowledgeReadModule` failures. The unchanged KnowledgeRead interface/S8W/S8S owner matrix
  plus S8Q1 is exactly `11 xfailed`. Complete no-external Canonical V2 is `296 passed, 141 skipped,
  26 xfailed` with no real failure.
- Complete Canonical V2 Pyright/Ruff and changed-test Ruff format/`py_compile` pass. Strict OpenSpec,
  `git diff --check`, scope/secret/cache, and package gates pass. The locked offline wheel retains
  SHA-256 `af7332f6...4d00`, contains 273 entries, and excludes `knowledge_read.py`, tests, and
  `.agents`. Candidate contract/test hashes are `1623d676...4503` and `cb0e8361...c62`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. Independent contract and two test
  final-gate reviews end zero Critical/Important/Minor/YAGNI.
- S8Q1 is Accepted only as a fixture RED predecessor. Task 8.1 reviewed calibration and claim-level
  oracle execution still await S2C; Tasks 8.1-8.3, 8.5, and 8.7-8.8 remain open. No production/
  shared code, provider, database, index, source, release pointer, Commit, Push, PR, archive, or
  Cutover changed.

## S10D Task 10.3 pure gap-remediation mechanics GREEN acceptance — 2026-07-15T06:47:34Z

- Extended the existing `KnowledgeGapFeedback` deep module with strict, immutable, content-bound
  offline remediation/effect receipts, request/result records, and one hidden transition/replay
  implementation. Task 10.3 stays unchecked and the global ledger stays 54/80 because this slice
  consumes only synthetic typed inputs, not Accepted query/answer operational effects.
- A candidate receipt produces only an unresolved linked gap. Resolution requires a different exact
  accepted candidate release, exact accepted release verification, and strictly later accepted
  intended-effect verification bound to the original gap, scope, traces, scenario, build, source
  batches, and receipt. Caller-final state, online evidence, incomplete lifecycle, cross-wires,
  duplicates, stale/tampered models, source-release self-closure, and time reversal fail closed.
- Constructed Pydantic requests and nested records are revalidated before lineage and replay lookup.
  Successful results are immutable and stable for the same exact request within an ephemeral
  instance even when its clock advances; changed input separates. The original input gap remains
  unchanged on every accepted and rejected path.
- Exact pre-GREEN execution was three `_MissingKnowledgeGapRemediationContract` failures after only
  removing the three S10C xfail wrappers. Final focused warnings-as-errors is `3 passed`; the exact
  S10A/S10B/shared-lifecycle/KnowledgeBuild/ReleasePublication owner matrix is `18 passed`.
  Complete no-external Canonical V2 is `299 passed, 141 skipped, 23 xfailed` with no real failure.
- Complete Canonical V2 Ruff and Pyright, changed-file format, strict OpenSpec, `git diff --check`,
  scope/secret/cache, and package checks pass. The final production/test SHA-256 values are
  `c611acd7...d7115` and `03dece88...be89`; Candidate contract SHA-256 is `17b2b66a...6160`.
  The locked offline 273-entry wheel SHA-256 is `78f4cd8a...a4791`; it contains the updated module
  and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. Two independent final reviews end
  zero Critical/Important. Nonblocking Minor: future long-lived instance cache bounds, opaque
  transition-ID content binding, and one base-gap rather than stale-gap loop assertion (the exact
  stale input was independently probed immutable). Nonblocking YAGNI: external receipt truth,
  universal remediation-kind rules, and cross-instance/concurrent/durable replay.
- S10D is Accepted as pure mechanics only. Task 10.3, Tasks 10.4-10.5, and aggregate S10 remain
  open. No provider, persistence, database/index/source, active pointer, Commit, Push, PR, archive,
  or Cutover changed.

## S8RF Tasks 8.3/8.5 retrieval-fusion/Web-handle RED acceptance — 2026-07-15T07:29:28Z

- Accepted one synthetic fixture-only RED predecessor through the single future
  `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` seam. Tasks 8.3/8.5 stay unchecked and the
  global ledger stays 54/80; no reviewed S2C case, real provider, persistence, or runtime acceptance
  is claimed.
- The first strict group executes all seven exact/structured/lexical/vector/relationship/internal-
  reference/Web lanes in one batch and proves real independent overlap without freezing scheduler
  width. Every recalled, fused, selected, rejected, or unresolved raw candidate retains exact query,
  lane, attempt, release, adapter/provider, score, evidence, and disposition trace. Person/
  Technology auxiliary results retain public origins and semantics without a fifth public domain or
  Product-capability propagation.
- The second group aggregates same accepted-ID aliases and local/Web evidence before hard constraints
  and late rerank, while same-name different accepted IDs remain separate. Ordinary quality gaps
  reach rerank; hard rejects retain exact failed-slot/evidence receipts. A hostile conflicting-ID
  merge fails to deterministic server-owned fusion, and wrong-bound/unknown/duplicate/timeout
  reranker output degrades with exact reasons without evidence loss or candidate resurrection.
- The third group gives two same-URL Web-only entities distinct session handles bound to snapshots,
  evidence, originating query/lane/attempt, and provider trace. Snapshot-byte tamper and independent
  live-provider change cannot replace the accepted snapshot; expired handles stop. Exact accepted-
  release lookup permits read-only resolution while wrong release, invented same-release ID, and
  wrong Canonical evidence reject with zero canonical/index/source-map mutation and unchanged input
  handle/snapshot/identity fixtures.
- Final focused normal execution is exactly `3 xfailed`; forced `--runxfail --tb=line` is three exact
  line-34 `_MissingKnowledgeReadModule` failures. Existing KnowledgeRead interface/S8Q1/S8W/S8S plus
  S8RF are exactly `14 xfailed`. Complete no-external Canonical V2 is `299 passed, 141 skipped, 26
  xfailed` with no real failure.
- Complete Canonical V2 Ruff/Pyright and changed-test Ruff format/`py_compile` pass. Strict OpenSpec,
  `git diff --check`, scope/secret/cache, and package gates pass. Candidate contract/test SHA-256
  values are `0d9af4e0...a5ae0` and `1fd10efe...9b0fc`. The locked offline wheel remains 273 entries
  at SHA-256 `78f4cd8a...a4791` and contains no `knowledge_read.py`, tests, or `.agents` artifact.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. Two independent final reviews on
  the exact identities end zero Critical/Important/Minor/YAGNI. Explicit later scope—not findings—
  includes ambiguity execution handoff, cross-session state, policy-owned max-bytes/oversize, and
  broader provider/schema permutations.
- S8RF is Accepted only as a fixture RED predecessor. Tasks 8.1-8.3, 8.5, and 8.7-8.8 plus aggregate
  S8 remain open. Adding a partial `knowledge_read.py` would awaken all 14 strict owner groups, so a
  GREEN slice must be atomic or first explicitly re-sentinel and re-accept those contracts. No
  production/shared code, provider, database/index/source, active pointer, Commit, Push, PR,
  archive, or Cutover changed.

## S8RG atomic KnowledgeRead synthetic mechanics GREEN acceptance — 2026-07-15T16:17:31Z

- Introduced one public `KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` deep module plus the
  package-internal ephemeral planner/factory. It makes the complete 14-group Accepted read-owner
  bundle and two new ambiguity-handoff/bounded-snapshot groups GREEN atomically without checking
  Tasks 8.1-8.3/8.5/8.7-8.8 or aggregate S8. The OpenSpec ledger remains 54/80.
- Planning preserves A-G, safety/enumeration, protected rewrite, institution, injected ambiguity,
  and internal Person/Technology behavior. Execution owns Universal Web, lane validation and full
  trace, content-addressed snapshot admission, identity/evidence-late fusion, protected constraints,
  structured rerank degradation, material-part sufficiency, bounded supplemental retrieval, and
  evidence-bound Web-handle replay/read-only resolution without persistence or query-time writes.
- Final review repairs close direct/candidate hard-constraint parity, evidence-subject/primary-
  identity cross-wires, accepted alias evidence, missing Web-handle execution context, supplemental
  constraint/max-result bypass, official-only source-trace loss, non-finite/negative supplemental
  budget values, forged supplemental lane, and universal/official max-results candidate-trace loss.
  Truncated raw candidates retain exact provider/evidence trace as `result_limit_rejected` and never
  enter fusion, rerank, or selection.
- Exact focused and owner results are `2 passed` and `16 passed`. Complete no-external Canonical V2
  is `315 passed, 141 skipped, 12 xfailed`; all 12 expected xfails belong only to untouched
  KnowledgeAnswer/S9 RED owners. Current complete Canonical V2 Pyright is zero findings; complete
  Ruff check, changed-file format, `py_compile`, strict OpenSpec, `git diff --check`, scope/secret/
  cache, and package checks pass. One untouched pre-existing KnowledgeAnswer test remains the only
  broader format-inventory finding and was not changed.
- Under the later managed sandbox, three full `.venv` attempts were externally terminated at 61%
  without a pytest failure or terminal result and are not counted as evidence. The approved read-
  only `uv run pytest` execution outside that sandbox completed the exact 315/141/12 matrix. The
  sandbox-local offline wheel attempt lacked cached `hatchling`; the approved local-cache offline
  build completed without network access.
- Locked production/test SHA-256 values are
  `0e9029942ea0d20ebe049e4000df283b871dcea2d1d3b711a7b90e2f391213b7` and
  `53787a215536ff9032ac16182e6d9055b9597b007ad4cc5ca589f38a87e810b0`. The fresh 274-entry wheel
  SHA-256 is `b5ed895f43f1a43476198b32af6af8887adcdc29454bc337bdbc016045d4994f`; it includes
  `knowledge_read.py` and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. No provider, persistence, database/
  index/source, active pointer, Commit, Push, PR, archive, or Cutover changed.
- Comprehensive independent review and the final exact-SHA two-finding delta review leave zero open
  Critical/Important findings. One nonblocking Minor records conservative negation substring recall
  loss; real-provider cancellation/latency calibration, cross-session equality, multi-snapshot live
  reconciliation, and broader provider/schema matrices remain downstream/YAGNI.
- S8RG is Accepted as synthetic mechanics only. S2C3C2 remains an external human gate only for
  reviewed Task 8.1 calibration and S8/S9 claim-level oracle execution; it is not a global Goal or
  independent-Ready-slice blocker.

## S8RG successor-shape compatibility correction — 2026-07-16T02:12:44Z

- The S9 atomic readiness audit exposed one Accepted predecessor-shape defect: non-
  `partial_coverage` continuation fixtures use `coverage_state=None`, while
  `ContinuationCandidate` required a string. A focused regression reproduced the Pydantic
  validation failure before production repair.
- `ContinuationCandidate.coverage_state` is now `str | None = None`. The atomic successor-shape
  regression carries both explicit `"open_world"` and explicit `None` candidates through the full
  JSON `EvidenceSet` round trip and verifies the absent state is preserved.
- Focused atomic and complete KnowledgeRead owner executions are `2 passed` and `16 passed`.
  Complete no-external Canonical V2 remains `315 passed, 141 skipped, 12 xfailed`, with all 12 xfails
  only in the untouched KnowledgeAnswer/S9 owners. Ruff check/format, `py_compile`, targeted Pyright,
  strict OpenSpec, `git diff --check`, secret/cache, and wheel-content checks pass.
- Corrected production/test SHA-256 values are
  `37420ec2075d4ed3527ad73c7960c5158f54057e5287d4cdc8cc0eb430a3bad0` and
  `d8e753331a55938ff7f894ddb397fea6cedaa9a0d6f6d05d1649fd7fd1979699`. The fresh 274-entry wheel
  SHA-256 is `53e56339ecaf107f6fc1c915f2261f27b8373078bbeb30fef30f9e0225446bba`; it contains
  `knowledge_read.py` and excludes tests/`.agents`.
- Independent review found one Important missing complete-result round-trip assertion. The targeted
  repair and re-review leave zero open Critical/Important/Minor/YAGNI. Original `pgtest` remains
  paused on exact volume `d81c6381...d241`; recovery remains network-none/no-port/restart-no;
  original Milvus SHA-256 remains `43ef203e...67cc`.
- S8RG is re-Accepted as synthetic mechanics only. No OpenSpec checkbox changed; the ledger remains
  54/80. No provider, persistence, database/index/source, active pointer, Commit, Push, PR, archive,
  or Cutover changed. The next independent candidate is the S9 atomic KnowledgeAnswer GREEN
  predecessor; reviewed S2C calibration/oracle execution remains downstream.

## S9AG atomic KnowledgeAnswer synthetic mechanics GREEN acceptance — 2026-07-16T03:36:43Z

- Introduced one package-local `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` deep module and an
  ephemeral factory. It atomically turns the S3A/S9A/S9G/S9M owners plus one new trust-boundary owner
  GREEN without checking Tasks 9.2/9.4/9.6/9.7/9.8 or aggregate S9. The ledger remains 54/80.
- Immutable request binding covers query, release, and the complete validated `EvidenceSet`.
  Recorded answer/assessment proposals are schema- and input-bound, revalidated even when supplied
  as same-class `model_construct` values, and treated only as proposals. Server logic owns claim/
  evidence/citation/conflict/status closure, Product insufficiency, Industry-Brief scope/coverage,
  assessment grounding, deterministic prose fallback, Canonical/Web context, typed traversal,
  ambiguity, topic switch, and at most three conditional continuation options.
- RED evidence was exact: the new group was one strict xfail/one exact forced target sentinel; the
  combined owner bundle was 13 strict xfails/13 exact forced sentinels; wrapper removal exposed
  exactly 13 target-module failures. Final focused/owner/full results are `1 passed`, `13 passed`,
  and `328 passed, 141 skipped, 0 xfailed`. The three warnings are intentional hostile
  `model_construct` serializer warnings in the atomic owner.
- The single merged independent review found three Important cross-path failures. Unsupported
  current-turn output could establish state before rejection; claim-suppressed clarification/refusal
  could still synthesize a Product insufficiency claim; and a first-current-turn unresolved Web
  source could traverse. Three regressions first failed exactly, then passed after transactional
  session restoration, suppression-aware Product handling, and source-first unresolved-Web refusal.
  Targeted exact-hash re-review returned `ACCEPTED` with zero Critical/Important/Minor/YAGNI.
- Complete Canonical V2 Pyright is zero findings. Scoped Ruff check/format, `py_compile`, strict
  OpenSpec, `git diff --check`, scope, high-confidence secret, generated-cache, and package checks
  pass. Accepted production SHA-256 is
  `4847de614c0f9fb6b080b1dad763d7e6f5300d91d1b2742b3d7426e4aee444b6`; atomic and multi-turn
  owner SHA-256 values are `c881c7cf...90048` and `4b252f85...ac13e`; the other three owners are
  unchanged from Candidate.
- The fresh 275-entry offline wheel SHA-256 is
  `e1fc009a49d57307834ab97fb34621cdfe859124dcd98294cb3e67f1c92e4419`; it includes
  `knowledge_answer.py`, `knowledge_read.py`, and `knowledge_gap_feedback.py`, and excludes tests/
  `.agents`. Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains
  network-none/no-port/restart-no; original Milvus remains `43ef203e...67cc`.
- S9AG is Accepted only as synthetic mechanics. Reviewed claim-level replay, completeness
  calibration, safety-guidance rendering, real provider/runtime behavior, durable sessions, full
  response acceptance, consumer migration, Commit, Push, PR, archive, and Cutover remain unchanged
  or downstream.

## S9C1 Task 9.7 continuation-offer acceptance — 2026-07-16T04:08:02Z

- Completed Task 9.7 through the existing `KnowledgeAnswer` deep module. A private immutable table
  now accepts only the six S9M-frozen reason/operation/target combinations, generates neutral server-
  owned labels, requires a non-empty relationship type only for executable next-hop traversal, and
  rejects relationship facts on non-traversal options. No public model or method changed.
- One public-behavior group first failed exactly once: invalid operation/target candidates survived,
  caller factual prose became an option label, and the three-option cap displaced a later valid
  candidate. After GREEN, only sanitized executable candidates survive in original order; valid
  handle/result-set, constraint, evidence, relation, source identity, and next-turn selection
  bindings remain exact; an invalid-only set yields no offer.
- The merged review found one Important remaining executable-contract gap: a traversal without
  `relation_type` and a non-traversal option with a stray relation were accepted. Both cases were
  added to the same group, reproduced one exact failure, and turned GREEN after a five-line fail-
  closed check. Targeted exact-hash re-review returned `ACCEPTED` with zero Critical/Important/
  Minor/YAGNI findings.
- Focused and multi-turn results are `1 passed` and `5 passed`; all KnowledgeAnswer owners are
  `14 passed`. Complete no-external Canonical V2 is exactly `329 passed, 141 skipped, 0 xfailed`.
  The three warnings remain intentional S9AG hostile-`model_construct` serializer warnings.
  Complete Canonical V2 Pyright is zero findings; Ruff check/format, `py_compile`, strict OpenSpec,
  `git diff --check`, scope, secret, generated-cache, and package checks pass.
- Accepted production/test SHA-256 values are
  `43207a6b2aa5619d6c7780af15ee06326c691f316f9b8b8c701b9f6fa37c8f41` and
  `faeba7a23db63143f39f3a5b090c1002607a3d717e3a5cef83064c1cb8aa077d`. The fresh 275-entry offline
  wheel SHA-256 is `17d82aa5ce6e0410904b7462d7337603320b1ed3766d00b4052a8312bbe90914`;
  it includes the three Canonical V2 read/answer/gap modules and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume `d81c6381...d241`; recovery remains network-none/
  no-port/restart-no; original Milvus remains `43ef203e...67cc`. No provider, persistence, database/
  index/source, active pointer, Commit, Push, PR, archive, or Cutover changed.
- Task 9.7 and its matching continuation acceptance criterion are Accepted, moving the formal ledger
  to 55/80. Aggregate S9 and Tasks 9.2/9.4/9.6/9.8 remain open; reviewed S2C oracle execution remains
  downstream rather than a blocker for independent mechanics.

## Existing incident/recovery checkpoint used as planning evidence

- Original `pgtest` was last verified paused; recovery work uses an isolated network-none lab.
- Forensic source/copy manifests and a verified partial FPI salvage dump exist outside the repository
  under `/home/longxiang/.mirothinker_recovery/20260711T022932Z-pgtest-forensic-freeze/`.
- A salvage-only isolated candidate checkpoint was restored and hash-checked before this change.
- These facts establish available evidence inputs; they do not accept Canonical V2, source coverage,
  or production parity.

## Spec evidence

- Requirements grill: `.agents/runs/canonical-v2-logical-rebuild/requirements-grill.md`
- Effect baseline: `.agents/runs/canonical-v2-logical-rebuild/outcome-requirements.md`
- Domain glossary: `CONTEXT.md`
- OpenSpec: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`

## S1 evidence checkpoint — 2026-07-11T05:05:30Z

- `docker inspect` reported `pgtest status=paused paused=true running=true`; host port remains
  `15432`, which is forbidden for S1 commands.
- Source volume identity matched
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- `pgtest-recovery-lab-01` reported `network=none` and no ports.
- Original Milvus hash matched
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Verified salvage dump hash matched
  `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`.
- Verification/slice contract and forbidden target rules exist. Tasks 1.1 and 1.2 are documentation
  complete; no implementation acceptance is claimed.
- S1 slice contract:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s1-database-target-safety.md`.

## S1 implementation evidence — 2026-07-11T05:37:16Z

### Candidate implementation

- Isolated code worktree: `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s1`, branch
  `canonical-v2-s1-safety`, based on `c0f3db2`; no commit or push was created.
- `src/data_agents/storage/database_target.py` defines one fail-closed destructive-target resolver.
  It accepts only Alembic config or dedicated `ALEMBIC_*` values for URL, expected database name,
  and target kind. Generic `DATABASE_URL` and `DATABASE_URL_TEST` are not migration inputs.
- The resolver rejects missing or conflicting explicit inputs, URL/name mismatch, unsupported target
  kind, system/real/recovery-checkpoint database identities, and host port `15432` before engine
  creation.
- `alembic/env.py` verifies `SELECT current_database()` after connecting and before configuring or
  running migrations. It also requires the database-side comment marker
  `miroflow:destructive-target:v1:<kind>:<database-name>`, then ends the identity queries' implicit
  read transaction before Alembic begins its migration transaction.
- The repository sibling search found one autocommit destructive test path that bypassed Alembic:
  `tests/postgres_seed_loader/test_seed_loader.py` used generic fallback before `DROP SCHEMA ...
  CASCADE`. It now resolves the same dedicated target and checks database name/marker before any
  schema DDL. Other located TRUNCATE/DELETE migration-test paths first cross the Alembic boundary;
  rollback-only/read-only database tests were not broadened.
- `alembic.ini` documents the explicit invocation contract. Historical migrations and ordinary
  runtime connection behavior were not changed.

### RED evidence

Command:

```text
cd apps/miroflow-agent
uv run pytest tests/storage/test_database_target_safety.py -n0 -q
```

Initial pre-implementation result: exit `1`, seven intended failures. The observed behaviors were generic
real URL precedence, acceptance of generic-only and known-real targets, no ambiguity/name/connected
identity checks, and rejection of an otherwise approved explicit target because the old environment
contract ignored it.

Self-review then identified that caller-provided kind/name was an attestation rather than independent
database-side proof. Two added RED cases (missing marker and wrong-kind marker) both failed because
the candidate still permitted migrations. Both became GREEN only after server-side marker checking
was implemented.

The sibling seed-loader regression also failed RED because a generic-only `DATABASE_URL` was still
accepted for an autocommit schema-drop fixture. It became GREEN after the fixture reused the shared
target resolver and database-side identity proof.

During real-Postgres validation, the first apparent V001→V042 run exited `0` but the target remained
at zero public tables. Read-only TCP/Unix-socket identity checks proved both paths addressed the same
database/OID/data directory. Root cause was the new identity `SELECT` opening a SQLAlchemy implicit
transaction that rolled back the migration transaction when the connection closed. A regression
assertion for ending that read transaction failed `0 == 1` before the one-line transaction-boundary
fix.

### Pure GREEN evidence

```text
uv run pytest tests/storage/test_database_target_safety.py -n0 -q
```

Final focused command in the lab network namespace:

```text
pytest tests/storage/test_database_target_safety.py \
  tests/postgres_seed_loader/test_seed_loader.py -n0 -q
```

Result: exit `0`, `15 passed`. The nine target-contract cases cover conflicting generic URL,
generic-only input, known non-disposable target, conflicting explicit sources, URL/expected-name
mismatch, connected database identity mismatch, missing/wrong database marker, and approved target
transaction cleanup. Six seed-loader cases cover its generic fallback rejection plus real
schema-drop/create cleanup and loader behavior on the proven disposable target.

Fail-closed CLI probes used an unresolvable host to prove no connection was required:

```text
generic_only_fail_closed=yes status=1
forbidden_explicit_fail_closed=yes status=1
wrong_database_marker_fail_closed=yes status=1
```

All probes matched the target-safety error rather than a DNS/connection error.

### Real isolated Postgres GREEN evidence

- Recovery lab: `pgtest-recovery-lab-01`, network `none`, no exposed ports.
- Newly created target: `miroflow_s1_disposable_20260711a`; it did not exist before this run and is
  distinct from both recovery checkpoint databases.
- Connection execution used the lab network namespace and `127.0.0.1:5432`; the explicit expected
  database was the same disposable name, target kind was `disposable`, and the database comment was
  `miroflow:destructive-target:v1:disposable:miroflow_s1_disposable_20260711a`.
- Before provisioning that exact marker, a real `alembic current` probe failed closed. After marker
  provisioning it returned `V042 (head)`; the marker persisted through downgrade and re-upgrade.
- Pre-upgrade: target identity matched, no Alembic revision, zero public tables.
- Upgrade: V001→V042 exited `0`; database state then reported V042, 42 public tables, and zero rows
  in each of `company`, `professor`, `paper`, and `patent`.
- Downgrade: V042→base exited `0`; database state contained only Alembic's empty version table.
- Second upgrade: V001→V042 exited `0`; final database state again reported V042, 42 public tables,
  and zero rows in all four domain tables.
- The real seed-loader suite exited `0` with six passes. Post-suite state remained V042 with 42
  public tables, no `seed_loader_test`/`seed_loader_empty_probe` schemas, and zero rows in the four
  domain tables.
- Final named database inventory still contained the two untouched recovery checkpoints plus the one
  new S1 disposable target.

### Static and source-invariant evidence

```text
uv run ruff check alembic/env.py src/data_agents/storage/database_target.py \
  tests/storage/test_database_target_safety.py \
  tests/postgres_seed_loader/test_seed_loader.py
# All checks passed

uv run pyright alembic/env.py src/data_agents/storage/database_target.py \
  tests/storage/test_database_target_safety.py \
  tests/postgres_seed_loader/test_seed_loader.py
# 0 errors, 0 warnings, 0 informations

git diff --check
# exit 0
```

Post-run read-only checks at `2026-07-11T05:37:16Z`:

- `pgtest`: `status=paused paused=true running=true`, port `15432`, source volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- `pgtest-recovery-lab-01`: `status=running network=none ports={}`.
- Original Milvus SHA-256 remained
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Verified salvage dump SHA-256 remained
  `cef8eb6ba18ebd23fde3e47023222ecb82bc8f27582040efe5a212a7f9fdfbb7`.

### Scope and review state

- No original `pgtest` command, unpause, connection, migration, or write occurred.
- No Milvus client was opened; only the original file hash was read.
- No recovery checkpoint database was a migration or test target.
- No domain schema revision, writer, retrieval/chat behavior, dependency, benchmark, commit, or push
  changed.
- Tasks 1.3 and 1.4 are complete. The user accepted the reviewed Candidate evidence at
  2026-07-11T05:39:19Z, completing task 1.5 and removing the S1 gate for future S2 planning.

## Next pending evidence

1. Task 5.2 decision-core implementation requires its own Ready slice. Task 5.1 RED acceptance does
   not authorize a production module, shared-contract/migration change, database write, or S5
   acceptance claim.

## S2 task 2.1 source inventory — 2026-07-11T07:11:30Z

- Branch/worktree: `canonical-v2-s2-baseline` at accepted S1 commit
  `a58184cee8d616cbcfc58c942f1b07790fc6ffdb`.
- Builder version: `canonical-v2-s2-source-inventory-builder-v1`; builder SHA-256
  `b94c29d6ec177df0dc43419e486e27eb1f6b55637abe05c868378cc57f85150c`.
- Inventory: `s2/source-inventory.json`, 48 source/family records, SHA-256
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`.
- Five TDD contract tests passed after observed RED failures. They prove byte hashing without source
  mutation, immutable/read-only SQLite access, Milvus-like hash-only treatment, deterministic family
  manifests, and committed/ignored/recovery/database source merging.
- Repeated full generation with identical inputs was byte-identical (`cmp` exit `0`).
- Recovery sessions used `PGOPTIONS=-c default_transaction_read_only=on` and proved current database,
  `transaction_read_only=on`, and data directory before counts. Both recovery checkpoints are V042
  with 42 empty public-domain tables and four salvage tables.
- Salvage counts: 99,437 distinct Papers; 101,158 distinct Professor-Paper links covering 2,826
  Professor source IDs and 97,285 Paper IDs; 20,773 field errors; 10 metadata rows.
- Large historical families include 11,604 Professor fetch-cache files, 26,185 OpenAlex cache files,
  351 SQLite snapshots, 1,544 data-agent JSONL files, 2,657 PDFs, and 97 Milvus-like files. Family
  records are content-addressed manifests; S4 must register individual artifact lineage.
- Original Milvus SHA-256 remained
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
  No verified copy was found, so S2 did not open any Milvus client or collection.
- Original `pgtest` remained `paused=true` on forbidden port `15432` with source volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`;
  recovery lab remained network-none with no published ports.
- No database/file source write, provider call, replay, migration, recollection, or production-code
  change occurred. Task 2.1 is complete; tasks 2.2–2.5 remain open.

## S2 task 2.2 source-to-PRD coverage matrix — 2026-07-11

- Reviewed `s2/source-coverage-matrix.md` against the task 2.1 inventory checkpoint
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`.
- The matrix separates four-domain object/sub-object evidence, relationship families, and
  exact/semantic/filter/relation retrieval reach from answer synthesis and operational readiness.
- Every gap records its evidence status, known ceiling, and future owning slice. In particular, the
  recovery public schemas are empty, Paper and Professor-Paper survive only in `salvage`, and no
  verified Milvus copy is available for index inspection or parity claims.
- The matrix covers all six confirmed effects: Knowledge coverage, Trusted data, Retrievability,
  Generation fidelity, Continuous operations, and Scenario acceptance. It treats the workbook as
  25 seed queries rather than a target-answer template.
- A deterministic inventory-to-matrix fact check verified workbook, source-family, published
  snapshot, and salvage counts. Contract checks verified all domain, relationship, outcome, and
  seed-corpus requirements. No database, provider, Milvus client, or source mutation was used.
- Task 2.2 is complete; tasks 2.3–2.5 remain open.

## S2 task 2.3 regression and challenge corpora — 2026-07-11

- Deterministic builder `s2/build_corpora.py` reads `docs/测试集答案.xlsx` without modification and
  emits 40 regression cases: 25 workbook rows across 17 conversation groups plus 15 PRD-derived
  cases. The separately versioned challenge corpus contains 12 cases: one user-reviewed badcase
  derived from workbook row 12 and 11 controlled variations.
- The user confirmed workbook answers/key points as case-specific reference ground truth. Each
  workbook case records row provenance and `user_confirmed_reference_gold`; the workbook remains a
  seed-query set rather than a general answer template or sole acceptance source.
- Workbook row 12 explicitly labels its historical response inaccurate. The corpus preserves it as
  a `known_bad_response`/`reviewed_badcase` and uses the key points as the correction constraint, so
  evaluation cannot reward reproducing the known-wrong response.
- PRD regression families cover exact, semantic, structured filter, relationship, A-G, multi-turn,
  Universal Web, provenance/conflict, partial answer, and evidence-based assessment. Challenges
  cover alias/spelling, time/geography/negation, relation direction, displayed-set/referent,
  topic-switch, provider failure, and insufficient evidence.
- Every case has A-G type, domain/family, source, protected slots, observable behavior, and review
  status. All A/B/C/D/E/G information-retrieval cases require Web augmentation; F refusals do not.
- Four TDD contract tests passed after observed RED failures for parser grouping, manifest hashes,
  required families, source resolution, F refusal/Web policy, and known-bad-response semantics.
  Ruff and Pyright passed with zero findings.
- Repeated full generation was byte-identical. Frozen SHA-256 values: regression
  `f2656e8c2f0803452af18fa0d478eec1b1e1b94eaa97ef48d06d0828401297da`, challenge
  `ee46c677af668131fb8da568fabd6386659f3287d0bdb0fd740f7069497f6f9f`, manifest
  `dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088`.
- PRD/challenge cases remain `pending_user_review` and the manifest remains
  `pending_user_acceptance`; they define observable behavior, not unreviewed factual gold. Task 2.3
  is complete; tasks 2.4–2.5 and S2 acceptance remain open.

## Backup/restore and offline-identity contract audit — 2026-07-11

- The user confirmed that Canonical V2 is a clean logical rebuild in a new isolated database, not a
  V042 patch. Existing proposal/design already satisfied this direction.
- The audit found that recorded source hashes and the salvage-only recovery proof did not establish
  complete backup coverage or independent recoverability for original PostgreSQL, original Milvus,
  WAL/FPI/salvage, and all inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source families.
- OpenSpec now requires a content-addressed source-to-backup manifest and a distinct second-target
  recovery/materialization drill. Hash equality alone is insufficient. Missing families, mismatches,
  failed probes, or unreviewed evidence fail closed before the first rebuild write.
- At this audit checkpoint, task 2.6 and Specified slice
  `slices/s2b-source-backup-restore.md` were added. Task 3.2 and every Canonical V2 schema, landing,
  canonical, publication, or index write were blocked until the later S2B acceptance recorded below.
- Canonical identity authority is now explicit: normalization, candidate recall, deterministic
  rules, structured LLM adjudication, human review, and merge/split publication belong to versioned
  offline builds. Query/answer paths may resolve user references against an accepted release but
  must emit an offline review gap instead of mutating identity/source mappings.
- This audit changed contracts only. At that checkpoint it did not create a backup, run a restore,
  access a database, open Milvus, or authorize any rebuild write; task 2.6 was still incomplete.

## S2 task 2.4 current/legacy/unavailable baseline — 2026-07-11T08:16:49Z

- Added deterministic builders/tests for the offline intent measurement and nine-dimension baseline
  report. Three builder contract tests passed after observed missing-implementation RED failures;
  Ruff and Pyright passed with zero findings.
- Exact offline check command removed `DATABASE_URL`, `DATABASE_URL_TEST`, Alembic, and Milvus
  variables and ran only the 100-case fixture contract plus deterministic rule fallback. Targeted
  pytest result: `2 passed, 1 deselected`; measured fallback intent accuracy: `100/100` overall and
  `100%` for every A-G class. This does not measure the provider-backed classifier, retrieval,
  rewriting, or answer behavior.
- `s2/baseline-report.json` SHA-256 is
  `c31b1c240ecc96661cf0b6c3057f02e631f34fcfae7356bb6f827cb5695352a1`; repeated generation from
  the same inputs was byte-identical. `s2/offline-intent-baseline.json` SHA-256 is
  `c7f68e5111250d84a2c30ab6712349d9d14772f636b021ea6d1e5c45c23624fa`.
- Current source evidence covers all four domains, while both recovery public schemas still have
  zero Professor/Company/Paper/Patent/relationship rows. Salvage retains 99,437 Papers, 101,158
  Professor-Paper links, and 20,773 field errors. Current service reach cannot be measured because
  there is no accepted canonical release or verified Milvus copy.
- Stored legacy evidence is retained without cross-population comparison: entity recall `30/41`
  (`73%`), Paper rollup `16/17` (`94%`), reviewed answer accuracy `10/19` (`53%`), multi-turn
  `1/18` passed with required recall `6/37`, and retrieval p95 `5.7089s`. These used changed V042,
  index, corpus, scorer, and/or provider conditions.
- Legacy precision remains unscored: the 12-row artifact is candidate capture, and its four-case
  label file is explicitly a scaffold. `0` listed unsourced-Web candidates is not Precision@K,
  ranking quality, Universal Web invocation, or claim-provenance acceptance.
- Current Recall@K, Precision@K/rank, answer support/citation, Universal Web, multi-turn, latency,
  provider calls, and cost are `unavailable`, not zero. Task 2.5 must freeze future thresholds and
  decide the evaluation-system replacement/calibration work without re-labeling legacy values.
- Source-invariant check passed with `set -e`: original `pgtest` remains paused on volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; original Milvus and salvage
  dump hashes match. An earlier composite check had an invalid Docker template and was discarded;
  the corrected fail-fast command produced the accepted evidence.
- No database query/write, Milvus client open, provider call, source mutation, backup claim, or
  rebuild write occurred. Task 2.4 is complete; task 2.5 owns the threshold freeze.

## S2 task 2.5 accepted threshold and corpus policy — 2026-07-11T15:10:32Z

- The immutable pending Candidate contains 83 metrics: 24 PRD minima, 25 hard invariants, and 34
  calibrated product-effect gates. Candidate SHA-256:
  `15a99c284861854b98a4bbfb0653700103f7b3b26e58079296f2c24e4c6c81d0`.
- TDD first produced two expected failures because the Candidate still reported
  `pending_user_approval`, then a third expected failure because no candidate-hash approval binding
  existed. GREEN added deterministic acceptance metadata and rejects any content whose SHA-256 does
  not match the reviewed Candidate.
- The Accepted registry SHA-256 is
  `bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc`. All calibrated values are
  `user_approved`; no PRD minimum, hard invariant, numeric threshold, population contract, or legacy
  baseline value changed during acceptance.
- The user explicitly approved the threshold Candidate, corpus ground-truth policy, and S2 tasks
  2.1–2.5. Workbook answers/key points remain case-specific reference ground truth; row 12 remains a
  known bad response with corrective key points. PRD/challenge cases are behavior contracts, not
  generated factual gold. Their immutable manifest retains its generation-time Candidate metadata,
  with this review providing the acceptance overlay.
- The population contract remains honest: the frozen 52 seeds do not materialize every later sample
  bank. Missing versioned/human-reviewed populations block only their owning metric and must be
  supplied by tasks 6.1, 8.1, and 9.1 without rewriting the seed corpus.
- Full S2 verification passed: all four S2 test modules reported `20 passed`; Ruff reported no
  findings; Pyright reported `0 errors, 0 warnings, 0 informations`; every S2 JSON/JSONL parsed;
  committed source/corpus/baseline/threshold hashes matched; regeneration of the Accepted registry
  was byte-identical; and strict OpenSpec validation exited `0`.
- Source invariants were rechecked at `2026-07-11T15:13:44Z`: original `pgtest` was still
  `paused=true` on the frozen volume, the recovery lab remained network-none with no ports, and the
  original Milvus plus verified salvage hashes matched. No database connection or Milvus client was
  opened by Task 2.5.
- Task 2.5 and S2 were Accepted at that checkpoint without authorizing task 2.6 or rebuild writes;
  the independently verified S2B acceptance is recorded below.

## S2B task 2.6 complete backup and independent restore — 2026-07-11T16:11:23Z

- Named targets were physically separated: backup root
  `/md1/mirothinker-backups/canonical-v2-s2b-20260711T152222Z` on device `2305`, independent restore
  root `/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z` on device `66306`, and
  primary evidence on device `2049`. Each target remained above the 50 GB capacity floor.
- Backup manifest SHA-256
  `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8` covers all 48 frozen
  inventory records plus original PostgreSQL and the complete forensic/WAL/FPI recovery tree. The
  inventory expands to 42,556 logical members and 16,447,082,378 bytes; all hashes and copy-
  independence checks passed.
- The original PostgreSQL volume was mounted only `rw=false` while `pgtest` remained paused. Its
  3,762-entry, 418,849,280-byte archive SHA-256 is
  `509cf117eae7ae3069e8d41d247044cd43168086b33b231590d9605546288da9`.
- The 24,230-entry forensic tree archive SHA-256 is
  `59f5901ecae7f612848ce7142031ad1efa1c366ce00a50b99019732b2d4d1055`. It includes retained WAL,
  FPI pages, ext4 journal/inode evidence, salvage and checkpoint dumps, forensic PostgreSQL bytes,
  IDs, plans, tools, and metadata. Only the active derived recovery-lab PGDATA was excluded; its
  immutable dump/checkpoint inputs are included and the original volume is backed separately.
- Restore verification SHA-256
  `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231` reports 50/50 sources
  passed. The 48 inventory records rematerialized with 42,556 hash checks and 86 bounded format
  probes. The forensic tree manifest matched exactly; both dumps, one WAL record, 20,427 FPI pages,
  and an ext4 journal block passed their format probes.
- PostgreSQL exact materialization matched all 3,762 tree entries. A second labeled probe volume ran
  with network none/no ports/read-only rootfs and proved `miroflow_real`, Alembic `V042`, 42 public
  tables, and zero Company/Professor/Paper/Patent rows. The failed initial `postgres`-role assumption
  was diagnosed as a probe bug; the original non-secret configured role `miroflow` succeeded without
  creating or changing roles.
- Original Milvus was never opened. A third verified probe copy opened six collections with 70,780
  rows; neither original nor first restored copy changed, and the probe copy hash was unchanged.
- A sibling-pattern audit found Postgres-image implicit anonymous volumes in S2B tool containers.
  RED/GREEN mount-policy coverage now requires an exact persistent allowlist and explicit PGDATA
  tmpfs override. Seven volumes attributable by ID/time were proved anonymous, dangling,
  unreferenced, and empty before exact removal; no recent anonymous dangling volume remained.
- Pre-acceptance verification passed 32 tests, Ruff, Pyright, full inventory regeneration, exact
  archive/source hashes, capacity/target isolation, source invariants, strict OpenSpec validation,
  and a temporary exact-hash admission run. Formal acceptance record SHA-256 is
  `3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b`; the formal gate reports
  `state=accepted`, `source_count=50`.
- Final post-acceptance verification at `2026-07-11T16:19:12Z` repeated all 32 tests, Ruff, Pyright,
  formal admission, artifact/control hashes, full inventory regeneration, capacity, target/source
  identities, and strict OpenSpec validation. The backup root is read-only (`dr-x------`); its
  control-evidence manifest SHA-256 is
  `59473d1739a5b072d9118d0fc76f92caa028d754c421d88a0c94e6db25d670f2`.
- No original source write, provider call, recollection, Canonical V2/landing write, or production-
  like cutover occurred. Task 2.6 is complete; the next task is 3.1.

## S3A task 3.1 deep-module RED interfaces — 2026-07-11T16:31:48Z

- Added one public-interface contract for each OpenSpec design seam: `EvidenceLanding.ingest/stream`,
  `KnowledgeBuild.build`, `KnowledgeRead.execute`, `KnowledgeAnswer.answer`, and
  `ReleasePublication.verify/promote/rollback`.
- The tests use typed request/result construction and local recording adapters to assert only
  caller-visible outcomes: evidence byte identity/lineage, isolated candidate manifests, protected
  query/evidence traces, material claim-evidence mapping with local/Web disclosure, and exact
  release parity/promotion/rollback. They do not assert tables, collection names, helper calls,
  execution order, or mock call counts.
- Each test is `xfail(strict=True, raises=ModuleNotFoundError)`. The normal command
  `uv run pytest tests/canonical_v2/test_*_interface.py -n0 -q` exited `0` with exactly five xfails
  and no failure/error/XPASS. The same command with `--runxfail` exited `1` with exactly five
  missing-`canonical_v2` failures and no collection/syntax/setup error.
- The strict marker is temporary executable RED evidence: unexpected failures are not swallowed,
  and a future implementation that satisfies a contract becomes XPASS/failure until the marker is
  intentionally removed by its GREEN task.
- Ruff passed and Pyright reported zero findings for all five files. The existing S2/S2B suite
  remained `32 passed`; formal backup admission remained Accepted for 50 sources; strict OpenSpec,
  original pause, Milvus hash, and salvage hash checks passed.
- No production source file, dependency, schema, database/index, provider, or original evidence was
  touched. Task 3.1 is Accepted under the user's self-approval authorization; task 3.2 must establish
  a separate Ready isolated-write slice before any database change.

## S3B task 3.2 clean database baseline — 2026-07-11T16:58:23Z

- The Ready slice fixed the boundary before writes: a separate Canonical V2 Alembic root, exact
  S2B admission before engine creation, S1 target identity before DDL, eight empty business
  namespaces, and no Task 3.3/3.4 tables or constraints.
- RED first reported `6 failed, 1 skipped`: the gate module was absent in five cases and the
  dedicated Alembic config/root was absent in one. After the isolated empty target was provisioned,
  the opt-in real test also failed at the missing Alembic root while the database remained at zero
  public tables and zero Canonical V2 schemas.
- `rebuild_write_gate.py` now binds the exact source inventory
  `83a9e2c8…0fa09`, backup manifest `a14c1eab…e59c8`, restore verification
  `98826e8d…d231`, and acceptance record `3155d890…fc5b`. Missing, byte-changed, non-accepted,
  coverage-mismatched, or failed-probe evidence rejects before migration engine creation.
- `canonical_v2_alembic` is a one-revision independent history: base/head `C2_0001`, branch
  `canonical_v2`, no V042 ancestry, and a distinct `public.canonical_v2_alembic_version` table. The
  revision creates only `landing`, `knowledge`, `professor`, `company`, `paper`, `patent`, `publish`,
  and `ops`; downgrade uses reverse-order non-cascading drops.
- The new target is `miroflow_canonical_v2_candidate_s3b`, marker
  `miroflow:destructive-target:v1:isolated-candidate:miroflow_canonical_v2_candidate_s3b`, system
  identifier `7661313446684311592`, container `canonical-v2-s3b-pg-20260711`, and named labeled
  volume `canonical-v2-s3b-pgdata-20260711`. It is healthy with network `none`, ports `{}`, restart
  policy `no`, and only a dedicated host-local Unix socket.
- The first socket used mode `0770`, but postgres retained primary GID 999 rather than the requested
  supplemental group, so host connection was denied. No migration ran. Recreating only the
  container over the same empty target volume with a `0777` socket inside a `0770` host directory
  preserved network/port isolation and limited traversal to postgres plus the workspace user.
- The real integration test deliberately set generic `DATABASE_URL` to the forbidden
  `localhost:15432/miroflow_real` value while providing the explicit Unix-socket candidate target.
  It passed base → `C2_0001` → base → `C2_0001`; final inspection found eight schemas, zero business
  tables, and zero legacy/extra public tables. Task 3.4 later invalidated the raw dump SHA because
  PostgreSQL 16 randomizes `\\restrict` control tokens; disposable replay produced deterministic
  normalized C2_0001 fingerprint
  `4c9df650d4f039ca9ba67ff6169ef44c839e0610528c2b27c4338eeeddf454c3` over 3,054 bytes.
- Final checks: Canonical V2 `7 passed, 5 xfailed`; S1 safety `9 passed`; S2/S2B `32 passed`; Ruff
  clean; Pyright `0 errors, 0 warnings, 0 informations`; strict OpenSpec and diff checks passed.
  Formal admission remained `state=accepted`, `source_count=50`; original `pgtest` stayed paused on
  its exact volume, recovery lab stayed network-none/no-port, and original Milvus/salvage hashes
  matched.
- Task 3.2 is Accepted under the user's self-approval authorization. The database is only an empty
  accepted foundation; Task 3.3/3.4 must add typed contracts/tables in separate Ready slices.

## S3C task 3.3 shared typed contracts — 2026-07-11T17:15:42Z

- Domain-model review confirmed the approved glossary already distinguishes Canonical V2,
  canonical/derived relations, relationship exploration, inclusion, and path eligibility. No new
  product term or glossary conflict required a protected `CONTEXT.md` change.
- Focused RED was `15 failed`, all caused solely by the absent
  `src.data_agents.canonical_v2.contracts` module. No test collection, fixture, or syntax failure
  occurred.
- The new single shared seam defines 26 frozen, extra-forbid Pydantic models and 20 workflow enums.
  It covers byte-addressed artifacts; replayable parser records and typed errors; temporal field and
  relationship assertions; selected/unresolved canonical decisions; source/canonical identities and
  merge/split/reversal lineage; canonical/derived/session relationships; versioned policies;
  knowledge gaps; and candidate/publication/manifests.
- Validators target hard contradictions rather than completeness gates: SHA and timezone identity,
  parent lineage, typed non-parsed errors, valid intervals, decision evidence membership,
  merge/split shapes, canonical-vs-derived evidence semantics, named hard exclusions, verified gap
  resolution, one-release manifests, and zero-deviation accepted parity. Partial records, competing
  assertions, unresolved decisions, optional enrichment, soft limitations, open catalogs, and
  opaque non-legacy IDs remain valid.
- Physical table/column/collection/provider contracts and typed domain business facts are absent.
  Build manifests instead retain source/parser/policy/model/decision/object/relationship/
  eligibility/publication/index versions, counts, and hashes through logical projection identities.
- Focused GREEN was `15 passed`. An initial Pyright finding identified the Python enum-member name
  `split` colliding with `str.split`; renaming only the member to `split_identity` retained external
  value `"split"` and produced zero Pyright findings.
- Expanded Canonical V2 checks were `21 passed, 1 skipped, 5 xfailed`: the opt-in real migration
  cycle was deliberately not run because this slice is DB-write-free, while all Task 3.2 gate/static
  checks and Task 3.1 strict RED contracts behaved as expected. S1 was `9 passed`; S2/S2B was
  `32 passed`; Ruff, strict OpenSpec, formal admission, and diff checks passed.
- Read-only candidate inspection preserved database/marker/system identifier
  `7661313446684311592`, revision `C2_0001`, eight schemas, and zero business tables. Original
  `pgtest` remained paused on its exact volume, recovery lab remained network-none/no-port, and
  original Milvus/salvage hashes matched. No database/Milvus/provider/source/runtime/dependency write
  occurred.
- Task 3.3 is Accepted under the user's self-approval authorization. Task 3.4 must map these logical
  values to integrity-tested storage in a separate Ready slice.

## S3D task 3.4 schema integrity migration — 2026-07-11T17:48:21Z

- Task interpretation was effect-first: S3 could not become an adapter-ready foundation with empty
  namespaces plus RED-only storage tests. Task 3.4 therefore used real tests to drive the smallest
  C2_0002 shared evidence/decision/release storage GREEN, without implementing S4–S7 module
  orchestration or typed domain facts.
- The first real disposable run was `7 failed`: two absent-C2_0002 revision failures and five
  undefined-table failures across actual SQL paths. The marked DB was
  `miroflow_canonical_v2_s3d_disposable`, inside the existing network-none/no-port S3B container;
  generic `DATABASE_URL` was deliberately set to forbidden `localhost:15432/miroflow_real` and was
  not used.
- First GREEN was `7 passed`. Self-review then challenged both precision and breadth: exact source
  and verified copy artifacts must coexist with identical bytes; parser-run/source-identity
  operational metadata must progress without rewriting evidence; and a build manifest hash must
  match its release. Those regressions produced the expected `3 failed, 6 passed`; revised DDL then
  produced `9 passed`.
- C2_0002 creates 24 shared tables across `landing`, `knowledge`, and `publish`, 126 named
  constraints, and 19 append-only triggers. It keeps `ops` and all typed domain schemas table-free.
  Named composite FKs prevent cross-release canonical endpoints; logical unique constraints prevent
  parser replay/assertion duplicates; immutable evidence/assertion/decision rows reject update and
  delete while operational parser/source-identity metadata remains updateable.
- Reversible identity decisions use a same-release self-FK and retain original plus reverse rows.
  Build manifests are release/hash-bound. The singleton serving pointer requires canonical,
  published-projection, and index release IDs to equal one manifest-backed active release; nested
  transaction rollback restored the prior pointer without deleting either release manifest.
- Downgrade names objects in reverse dependency order without CASCADE, returns to exactly the eight
  C2_0001 schemas, and re-upgrades to C2_0002. All fixture transactions rolled back. Disposable and
  durable candidate each reported C2_0002, 24 tables, zero rows, 126 constraints, and 19 triggers.
- A pattern audit proved raw PostgreSQL 16 schema-dump SHA values were volatile because every dump
  changes random `\\restrict`/`\\unrestrict` lines. Only two sibling claims existed, both in Task
  3.2 evidence. `scripts/canonical_v2_schema_fingerprint.py` now removes only those control lines;
  two tests prove random-token stability and real schema-change sensitivity.
- Corrected C2_0001 fingerprint is
  `4c9df650d4f039ca9ba67ff6169ef44c839e0610528c2b27c4338eeeddf454c3` over 3,054 normalized bytes.
  C2_0002 candidate/disposable fingerprint matched at
  `ffeb1c92cb6dbc5ee9475b37142f632250b21dd97beb5da02a7f0642a64b6faf` over 50,032 bytes, with two
  random control lines removed from each.
- The sibling audit also found Task 3.2's baseline test was coupled to the durable candidate and
  dynamic head. After C2_0002, that could downgrade a future populated candidate and falsely require
  head to contain no tables. RED was reproduced on the disposable; the test now requires target kind
  `disposable`, verifies fixed revision C2_0001, and restores current head in `finally`.
- Real migration/integrity/fingerprint verification was `13 passed`; normal no-DB Canonical V2 was
  `23 passed, 10 skipped, 5 xfailed`; S1 was `9 passed`; S2/S2B was `32 passed`. Ruff, Pyright,
  strict OpenSpec, formal admission, and diff checks passed.
- After matched evidence capture, the disposable database was dropped. Durable
  `miroflow_canonical_v2_candidate_s3b` remains healthy, network-none/no-port, system identifier
  `7661313446684311592`, at C2_0002 with 24 tables and zero rows. Original `pgtest` stayed paused on
  its exact volume; recovery lab isolation and original Milvus/salvage hashes matched.
- Task 3.4 is Accepted under the user's self-approval authorization. This does not accept the whole
  S3 foundation; Task 3.5 owns that independent review.

## Task 3.4 pattern-fix report

- Reported cases fixed: nondeterministic schema-dump hashes and a baseline rollback test whose
  target/revision scope became unsafe after a second migration.
- Defect class: volatile command output treated as content identity; destructive tests bound to a
  durable target and dynamic head.
- Sibling search: all repository schema-dump/hash claims and Canonical V2 migration rollback tests.
- Sibling issues found/fixed: two raw Task 3.2 hash claims and one candidate-bound baseline test.
- Not fixed: no other matching schema-hash claim or Canonical V2 destructive test exists.
- New invariant/helper/test: normalized fingerprint CLI plus two tests; disposable-only fixed-
  revision baseline test with current-head restoration.
- Remaining risk: new dump evidence must use the helper; new destructive migration tests must use
  freshly marked disposable databases.

## S3E task 3.5 independent foundation review — 2026-07-11T18:22:18Z

- Independent review compared S3 commits `905ca35..e7fffe2` and the repair candidate against the
  OpenSpec design/specs, shared contracts, DDL, real tests, and predecessor gates. The full finding
  matrix and disposition are in `s3-foundation-review.md`; no Critical/Important finding remains.
- First review RED was eight serial database failures plus one contract failure: parent hashes were
  not bound to parent bytes, assertion endpoints were not bound to record/identity mappings,
  append-only history allowed bulk truncate, decision history could not cross releases, structured-
  LLM traces had no storage, and relationship assertions could use canonical endpoints.
- A default-xdist RED attempt produced one failure plus seven migration setup errors because workers
  raced the same disposable database. This was classified and fixed as a destructive-test harness
  defect; the Canonical V2 subtree now selects zero automatic xdist workers, and its default command
  ran serially.
- Second review RED added four database failures and two contract failures for mutable parser/source-
  identity provenance rewrite/delete and self-referential decision lineage. A final review pass added
  two wrong-subject supersession failures and one wrong-policy contract failure.
- C2_0003 repairs the complete defect class without rewriting C2_0001/C2_0002: composite artifact
  hash and record/identity provenance FKs; truncate guards; field-aware parser/source-identity
  mutation guards; globally unambiguous cross-release decision lineage bound to the same logical
  subject and never itself; and schema-validated JSONB LLM traces on identity, field, and
  relationship decisions.
- Shared contracts now require field-selection policy for canonical decisions, source identities for
  source-grounded relationship assertions, and non-self decision lineage. Future EvidenceLanding,
  KnowledgeBuild, and ReleasePublication modules must re-export the shared record/candidate/release
  types rather than create drift-prone duplicates.
- Full default Canonical V2 verification was `47 passed, 5 xfailed`; forced RED was exactly five
  `ModuleNotFoundError` failures for the future deep modules. The real disposable exercised base/
  C2_0001/C2_0002/C2_0003 downgrade/re-upgrade and all fixture rows rolled back.
- Two disposable dumps and the durable candidate dump normalized identically to
  `7d85702ecb0e84cbbbbbc175f88c4b735190e53f4a576c72e49088899dd94991` over 63,875 bytes, removing
  exactly two random PostgreSQL control lines. Both targets reported 24 shared tables, zero rows,
  141 constraints, 44 non-internal triggers, and three LLM-trace columns at C2_0003.
- Durable candidate `miroflow_canonical_v2_candidate_s3b` was forward-upgraded only after GREEN and
  exact gate/name/marker/system/network/volume proof. The test-only disposable was then dropped.
- S1 safety was `10 passed, 5 explicit skips`; S2/S2B was `32 passed`; Ruff passed; Pyright reported
  zero findings; strict OpenSpec and diff checks passed. Formal admission remained `accepted/50`.
  Original `pgtest` stayed paused on its exact volume, recovery lab stayed network-none/no-port, and
  original Milvus/salvage hashes matched.
- Task 3.5 and all S3 are Accepted under the user's objective-verification self-approval
  authorization. Task 4.1 remains unstarted until its own Ready slice.
- Final read-only invariant check at `2026-07-11T18:25:59Z` re-proved formal admission
  `accepted/50`, candidate C2_0003/24 tables/zero rows/141 constraints/44 triggers, disposable
  absence, original pause/volume, recovery isolation, and both source hashes.

## Task 3.5 pattern-fix report

- Reported cases fixed: audit-chain gaps across interface types, artifact/record identity,
  append-only/mutable history, reversible decisions, LLM trace storage, and test concurrency.
- Defect class: typed audit intent was present in names/models but not closed across interface,
  storage, cross-release lineage, bulk mutation, and test-execution boundaries.
- Sibling search: all three decision families, every append-only/mutable history table, all source-
  assertion endpoint paths, all Task 3.1 shared-type candidates, and all Canonical V2 destructive
  migration tests.
- Sibling issues found/fixed: three trace columns/checks, three decision lineage families, nineteen
  append-only truncate triggers, two mutable-history field/delete guards, artifact plus three
  assertion provenance FKs, three shared public type exports, and one subtree-wide xdist guard.
- Not fixed: later-slice repositories still own association cardinality and transactional build
  semantics; ReleasePublication owns verification/state authorization; domain/ops storage remains
  intentionally absent. None is exposed as accepted behavior in S3.
- New invariant/helper/contract/test: C2_0003 plus real RED/GREEN matrix; shared-contract validators;
  default-serial Canonical V2 DB tests; deterministic matched candidate/disposable fingerprint.
- Remaining systemic risk: later writers must enter through the shared typed/deep-module seams and
  add their own real transaction tests; direct caller SQL is not an accepted interface.

## S4A task 4.1 immutable landing RED — 2026-07-11T18:33:37Z

- The approved design keeps `EvidenceLanding.ingest/stream` deep and storage-independent. Task 4.1
  therefore targets a future concrete ephemeral composition through those public methods, rather
  than a local subclass that fabricates receipts or direct C2 table assertions that would leak Task
  4.3 storage.
- Four independent scenarios freeze observable effects: exact content hash and distinct source/copy
  artifacts with parent lineage plus mismatch rejection before streaming; same-artifact replay with
  distinct immutable parser v1/v2 record/run identities; partial and corrupt rows retaining readable
  payload plus typed field/record errors; and unreadable identity fields producing neither
  placeholders, parent IDs, canonical IDs, nor an active-release change.
- Synthetic historical-JSONL bytes include one explicit unreadable-external marker and one corrupt
  line solely to define the representative contract. No real recovery/historical/provider source was
  opened or replayed; Task 4.2 owns adapter implementation and Task 4.4 owns the bounded source
  matrix.
- Normal focused pytest was exactly `4 xfailed`. Forced `--runxfail` was exactly `4 failed`; every
  failure was `ModuleNotFoundError: src.data_agents.canonical_v2.evidence_landing`, with no syntax,
  fixture, collection, or assertion error.
- Normal Canonical V2 regression was `23 passed, 24 skipped, 9 xfailed`: real database cases skipped
  without explicit test target, the original five Task 3.1 seams remained strict RED, and the four
  new landing cases were the only additional xfails. S1 was `10 passed, 5 explicit skips`; S2/S2B
  was `32 passed`; Ruff and Pyright reported no findings.
- Strict OpenSpec and diff checks passed. Formal S2B admission, original pause/volume and source
  hashes, recovery isolation, and the zero-row C2_0003 candidate remained unchanged. No production
  module, migration, database, source, Milvus, provider, dependency, or runtime behavior changed.
- Task 4.1 is Accepted under the user's objective-verification self-approval authorization. This
  accepts only RED behavior; S4 remains unaccepted and task 4.2 has not started.
- Final read-only check at `2026-07-11T18:35:00Z` re-proved formal admission `accepted/50`, original
  pause/volume and hashes, recovery/candidate isolation, and candidate C2_0003/24 tables/zero landing
  or release rows.

## S4B task 4.2 EvidenceLanding and source adapters — 2026-07-11T19:06:55Z

- The implementation follows the approved deep-module boundary: `evidence_landing.py` owns strict
  request/receipt/parser/draft types, exact-byte and pre-parse parent-lineage checks, separate
  request/output fingerprints, deterministic identities, atomic visibility, replay retention, and
  the public `ingest/stream` seam. `evidence_adapters.py`
  owns format parsing only. Its composition uses an internal ephemeral repository; Task 4.3 still
  owns PostgreSQL persistence and Task 4.4 still owns actual-source matrix replay.
- Four pre-implementation adapter scenarios failed exactly with `ModuleNotFoundError` and covered
  verified WAL/FPI salvage envelopes, shared JSON/CSV/XLSX/SQLite record behavior, verified-copy-
  only Milvus exports, and already-collected response provenance. The Task 3.1 EvidenceLanding plus
  four Task 4.1 effects and those four adapter cases then produced an initial `9 passed` GREEN.
- Adapters consume only supplied immutable bytes. SQLite materializes those bytes to a temporary
  file opened with `mode=ro&immutable=1`; XLSX uses read-only mode; WAL/FPI and Milvus accept verified
  record envelopes rather than opening original stores; collected responses contain no acquisition
  or provider client. No original/recovery path or real source was opened by the implementation or
  behavior tests.
- Candidate self-review first found three escaped sibling defects. A repeated run ID did not fingerprint
  parent lineage, CSV/XLSX could silently overwrite duplicate columns, and collected-response
  provenance checked field presence without validating field shape. Three new regressions produced
  the expected `3 failed`; the shared fixes bind both parent identifiers, quarantine duplicate CSV
  and XLSX headers before row construction, and preserve invalid response envelopes as partial
  evidence with field-specific typed errors.
- A second immutable/silent-loss audit found six sibling failures: observation time was absent from
  run identity, returned payloads could mutate repository state, unheaded CSV cells were discarded,
  JSON duplicate keys used last-write-wins, boolean/empty Milvus identifiers passed, and a non-time
  retrieval string passed provenance validation. All six failed before their shared fixes and then
  passed. Final focused landing verification was `16 passed`.
- Default Canonical V2 verification was `39 passed, 24 skipped, 4 xfailed`; all skips require an
  explicit disposable database and all four xfails are the untouched future KnowledgeBuild,
  KnowledgeRead, KnowledgeAnswer, and ReleasePublication seams. Forced interface execution was
  exactly one EvidenceLanding pass plus those four `ModuleNotFoundError` failures. S1 was
  `10 passed, 5 explicit skips`; S2/S2B was `32 passed`.
- Focused Ruff passed and Pyright reported zero errors/warnings/information. Strict OpenSpec and
  `git diff --check` passed. No dependency, migration, database/schema row, actual source replay,
  Milvus client, provider call, canonical/publication/index state, or legacy runtime consumer
  changed.
- Final read-only evidence re-proved formal admission `accepted/50`; original `pgtest` is paused on
  volume `d81c6381…d241`; recovery and candidate containers remain network-none/no-port; original
  Milvus and salvage hashes remain `43ef203e…67cc` and `cef8eb6b…bb7`. The candidate marker and
  system ID match, revision is C2_0003, and it has 24 tables, 141 constraints, 44 non-internal
  triggers, and exactly zero rows across all Canonical V2 business tables.
- Task 4.2 is Accepted under the user's objective-verification self-approval authorization. This
  accepts only the ephemeral core and safe source adapters; S4 remains unaccepted, and task 4.3 has
  not started.

## Task 4.2 pattern-fix report

- Reported cases fixed: conflicting parent/time hidden behind one run ID; returned snapshots
  mutating retained evidence; duplicate or unheaded structured values being overwritten/discarded;
  ambiguous JSON, Milvus identifiers, and collected-response provenance treated as parsed.
- Defect class: evidence identity or shape checks were locally present but incomplete across
  idempotency, sibling structured adapters, and provenance fields.
- Sibling search: run/artifact/parent/time fingerprints and conflict paths; stream snapshot
  ownership; CSV/XLSX header and row-to-payload paths; every JSON-based adapter; Milvus record
  identity; every required collected-response provenance field.
- Sibling issues found/fixed: parent identity and normalized observation time enter the run
  request fingerprint before lineage/parse, while parser output remains separately fingerprinted;
  stream returns deep snapshots; CSV/XLSX enforce structural uniqueness and CSV keeps mapped fields
  with typed overflow errors; every JSON adapter rejects duplicate object keys; Milvus rejects
  empty/boolean identity; response URL/time/status/content type receive field-specific validation
  without discarding readable body bytes.
- Not fixed: durable cross-process idempotency and transactions belong to Task 4.3; real source-
  format/count compatibility belongs to Task 4.4. Neither is claimed by this ephemeral slice.
- New invariant/helper/contract/test: complete-run idempotency regressions, detached stream snapshot,
  cross-format duplicate-header and JSON matrices, CSV overflow preservation, invalid Milvus/
  provenance regressions, strict JSON loader, and non-shared parser defaults.
- Remaining systemic risk: adapters added later must apply the same pre-construction uniqueness and
  typed-degradation rules; Task 4.3 must re-prove atomicity/idempotency against real PostgreSQL.

## S4C task 4.3 durable EvidenceLanding — 2026-07-11T19:42:20Z

- The Task 4.2 core now depends on a small repository protocol for pre-parse admissibility, atomic
  prepared-run commit, and ordered stream. Hashing, adapter behavior, typed records, receipts, and
  the `EvidenceLanding.ingest/stream` seam remain shared by the ephemeral and PostgreSQL adapters;
  storage table/SQL details do not enter the caller interface.
- Initial RED was exactly `6 failed`: Alembic could not resolve C2_0004, four real behavior paths
  could not import `evidence_landing_postgres`, and the forced-rollback path lacked a persistence
  error type. The explicit Unix-socket DSN addressed only the newly marked
  `miroflow_canonical_v2_s4c_disposable`; generic `DATABASE_URL` was deliberately set to forbidden
  `localhost:15432/miroflow_real` and was not selected.
- C2_0004 adds immutable `landing.ingest_run`, `parser_run.parser_options`, and
  `source_record.record_ordinal` plus composite lineage/parser FKs, fingerprint/status/count checks,
  uniqueness, and append-only/immutable triggers. Its upgrade transaction refuses any nonempty
  C2_0003 landing because original run identities cannot be reconstructed without invention. A real
  RED proved the old migration silently accepted such a row; GREEN proved the failed upgrade leaves
  both C2_0003 revision and original artifact intact.
- The PostgreSQL factory first requires an absolute exact Accepted S2B gate root, then resolves only
  explicit target URL/name/kind, verifies connected database name/marker and C2_0004, and rechecks
  the gate before every write connection. A relative path to the real Accepted root failed RED only
  after attempting DNS; the reordered gate now rejects it before connect. A read-only probe of the
  durable candidate correctly rejected its intentional C2_0003 revision without writing it.
- Commit takes a transaction-scoped advisory lock per run ID, rechecks request/output fingerprints
  and artifact lineage, then atomically inserts artifact, parser configuration, ordered records,
  ordered errors, and the ingest-run receipt. Exact concurrent repeats commit once; conflicting
  repeats add nothing; distinct concurrent runs share one artifact without losing either replay;
  a forced record-insert trigger rolls back every preceding row.
- Restart/replay reconstructs parser/schema identity, record order, payloads, and ordered typed
  errors through shared contracts. `ingest_run` rejects update/delete/truncate and parser options
  reject rewrite. Python's non-standard `NaN/Infinity` JSON behavior was found at the PostgreSQL
  boundary: two REDs showed ephemeral false-parse and JSONB batch failure; the shared strict loader
  now quarantines those records as corrupt while the batch commits.
- Final real disposable verification was `34 passed`, including repeated C2_0001↔C2_0004
  downgrade/re-upgrade, all prior shared-integrity tests, nine Task 4.3 scenarios, concurrency, and
  transaction rollback. Focused ephemeral landing was `17 passed`. Default no-DB Canonical V2 was
  `41 passed, 32 explicit skips, 4 xfailed`; forced interfaces remained exactly one EvidenceLanding
  pass plus four missing future modules. S1 was `10 passed, 5 explicit skips`; S2/S2B was
  `32 passed`; Ruff check/format, Pyright, strict OpenSpec, and diff checks passed.
- Immediately before deletion, the disposable matched its marker/system ID at C2_0004 with 25
  tables, 153 constraints, 46 non-internal triggers, both required landing columns, and zero total
  business rows. It was then dropped and its database count became zero. The durable candidate
  remained C2_0003/24 tables/zero rows; no actual source was replayed and no Milvus/provider,
  canonical, publication, index, dependency, or legacy runtime state changed.
- Task 4.3 is Accepted under the user's objective-verification self-approval authorization. This
  accepts durable module behavior and disposable migration evidence only; S4 remains unaccepted,
  task 4.4 must separately upgrade/populate the isolated candidate from a bounded verified source
  matrix, and no production-like cutover is authorized.

## Task 4.3 pattern-fix report

- Reported cases fixed: in-memory-only idempotency/replay, cross-process run and artifact races,
  partial transaction visibility, mutable ingest/parser history, relative gate acceptance,
  unaccounted nonempty schema upgrade, and non-standard JSON crossing the Python/JSONB boundary.
- Defect class: correct local evidence semantics were not yet closed across process, transaction,
  migration, target-admission, serialization, and database-constraint boundaries.
- Sibling search: request/output/artifact identities; same/different-run concurrency; parser options,
  record/error order, every landing mutation trigger; gate-root and target/revision checks; C2_0003
  upgrade states; all JSON-based source adapters.
- Sibling issues found/fixed: one repository seam and advisory-locked transaction; persisted complete
  run identity/configuration/order; append-only ingest/parser guards; absolute gate-before-connect;
  candidate revision refusal; fail-closed nonempty upgrade; strict duplicate and non-finite JSON.
- Not fixed: actual verified-source format/count compatibility, source-matrix throughput/capacity,
  landing checkpoint hash/count summaries, and durable candidate C2_0004 upgrade belong to tasks 4.4
  and 4.5. None is claimed by Task 4.3.
- New invariant/helper/contract/test: C2_0004 empty-landing admission; PostgreSQL repository protocol;
  restart/concurrency/rollback matrices; cross-layer strict JSON tests; per-test migration reset;
  explicit read-only candidate-behind-head rejection.
- Remaining systemic risk: Task 4.4 must use this public factory with the exact gate/target inputs,
  verify real source bytes before parsing, and prove bounded replay counts/errors without bypassing
  the repository or directly inserting landing rows.

## S4D task 4.4 bounded real-source landing matrix — 2026-07-11T20:33:12Z

- A Ready S4D contract froze six concrete members of the exact Accepted S2B checkpoint: the verified
  FPI salvage dump; `released_objects.db`; the eight-row Company knowledge JSONL; the one-row Patent
  identifier workbook; the 1.3 GB Milvus restore copy; and one verified Professor fetch-cache
  response. The matrix records complete source IDs, member/restore paths, sizes, source SHA-256,
  parser/schema/options, fixed selectors, and expected output summaries. Its SHA-256 is
  `eaba2ecb93f1418b90ece45e91d7071d638095897bdd6a2c012efe6a9db9a923`.
- Initial artifact/adapter RED was exactly seven failures: streaming artifact registration was
  absent, recorded-response provenance was rejected as the wrong source kind, and SQLite ignored or
  accepted invalid/non-deterministic bounds. Matrix/materializer RED was exactly five failures,
  followed by individual REDs for destination-before-preflight, selected COPY filtering, strict
  six-family loading, and two ambiguous-JSON cases. GREEN adds no fixture-only bypass: the same
  public ephemeral/PostgreSQL landing seams execute tests and the real replay.
- `RegisterArtifactRequest` hashes local files in 1 MiB chunks, validates stable file identity,
  expected size/hash and parent pair, and persists an artifact manifest without parser bytes. Both
  repositories retain it idempotently. This permits the accepted backup and restore Milvus/database
  artifacts to form real parent chains without loading 1.3 GB into memory. Direct restored files
  parent to their backup artifacts; WAL, Milvus, and recorded-response exports parent to restore
  artifacts, which parent to their backup artifacts.
- SQLite bounds accept only integer limits 1-1000 and require deterministic primary-key order. The
  historical recorded response keeps the known URL/body/cache hash/path while deliberately omitting
  unknown retrieval time, status, and content type; the shared response adapter preserves it as one
  partial record with three typed `schema_mismatch` errors rather than invent provenance. A complete
  newly collected HTTP envelope remains a later recollection input and is not claimed here.
- The task tool first executes the hard-coded Accepted/50 gate, verifies each selected member in its
  accepted member manifest, constrains all paths below distinct backup/restore roots, streams both
  file hashes/sizes, and rejects shared inodes. WAL extraction scans the verified custom dump in a
  read-only/network-none/tmpfs Docker invocation and retains only three fixed Paper keys/errors;
  every invocation proves the Docker volume set unchanged. Milvus opens only an inode-independent
  working copy of the verified restore, exports three fixed Company IDs/non-vector fields, and proves
  both working and restore hashes unchanged. Matrix/member/cache JSON rejects duplicate keys and
  non-standard numbers before paths or values are used.
- Two read-only real-source observe executions produced byte-identical summary files with SHA-256
  `f529a013e6ee3ea8f2a0b720ec67ea3ca4d4fc556f25ad5ce695e4e158e9277e`.
  Both reported six entries, 21 records, six typed errors, and entry-summary SHA-256
  `5b77b4a4f3ea9f0a0fd4667dfccff6afefa968b5fb43124de816e652d1c58293`.
  The frozen per-entry result is: WAL 3 partial/3 missing-external errors; SQLite 5 parsed; JSONL 8
  parsed; XLSX 1 parsed; Milvus 3 parsed; recorded response 1 partial/3 schema errors.
- Immediately before the first candidate schema write, the gate returned `accepted/50`; container
  isolation was network-none/no-port/restart-no; database name, isolated-candidate marker, and system
  ID `7661313446684311592` matched; revision was C2_0003; and all landing/business rows were zero.
  The candidate was upgraded forward only to C2_0004. No durable candidate downgrade was run.
- Durable replay uses only `create_postgres_evidence_landing`; there are no direct landing inserts.
  Resulting counts are 15 artifacts, six ingest runs, six parser runs, 21 source records, and six
  errors. Artifact kinds are six backup copies, three restore copies, three direct structured
  artifacts, and one each WAL/Milvus/recorded-response derived artifact. There are six roots and nine
  valid parent edges with zero orphan/hash-mismatched edges. Run states are four accepted/two partial;
  records are 17 parsed/four partial; errors are three missing-external/three schema-mismatch.
- Three durable script executions retained exactly those counts. The latter two checkpoint outputs
  compared byte-for-byte with the committed summary; all have SHA-256
  `a88b44fab38d4e56a7894fabb93e56b46c043278082c200773c038a7dc6e80b5`.
  The committed entry hash remains `5b77b4…c58293`. Every knowledge and publish table remains zero;
  no active release, canonical assertion/identity/decision, provider call, live recollection, or
  active/new Milvus index was created.
- Real disposable baseline/integrity/landing validation reported `35 passed`, including migration
  round trips, append-only/FK/reversal/release invariants, streaming parent registration,
  concurrency, rollback, and a candidate-behind-head regression that no longer depends on durable
  candidate state. The disposable was verified by exact marker and deleted; database count returned
  to zero. Default Canonical V2 reported `57 passed, 33 explicit skips, 4 expected xfails`; S1 was
  `10 passed, 5 explicit skips`; S2/S2B was `32 passed`.
- Final static verification passed Ruff check/format, Pyright with zero findings, strict OpenSpec,
  both JSON documents, and `git diff --check`. The final read-only audit at
  `2026-07-11T20:38:12Z` re-proved Accepted/50; original `pgtest` paused on exact volume
  `d81c6381…d241`; original/restore Milvus hash `43ef203e…67cc`; original/restore salvage hash
  `cef8eb6b…bb7`; recovery/candidate network-none/no-port isolation; candidate C2_0004 with 25
  tables and 46 non-internal triggers; 15/6/6/21/6 landing counts; six roots/nine matching parent
  edges/no orphans; zero non-landing rows; no disposable database; and exact matrix/summary hashes
  `eaba2ecb…a923` / `a88b44fa…e80b5`.
- At the Task 4.4 checkpoint it was complete only as a reviewable Candidate; Task 4.5 still had to
  independently review the whole landing slice and restore-verify its database dump before S4 could
  be accepted. No S4 acceptance or production-like promotion was claimed at that earlier point.

## S4E task 4.5 landing review and checkpoint — 2026-07-11T22:07:12Z

- Two independent read-only final reviews returned `Ready` with zero open Critical/Important
  findings. The review first blocked operation and drove systemic repair of exact target admission,
  source/inode revalidation, immutable evidence outputs, separate execution receipts, complete
  table/integrity hashing, final Postgres readiness, restore image/socket/storage policy, and
  owned-ID graceful cleanup. The accepted disposition is in `s4-landing-review.md`.
- Focused S4D/S4E RED began with 13 replay-guard failures and 10 missing-checkpoint failures. Final
  focused verification is `48 passed`; Ruff and Pyright report no findings. In addition to pure
  guards, a real read-only C2_0004 candidate snapshot executed all table and landing-integrity SQL.
- Fresh guarded replay ID `canonical-v2-s4-landing-20260711T215953Z-cef42a1` used the exact Task 4.4
  commit, current S4D tool hash, OpenSpec/worktree identity, Accepted/50 gate, and explicit candidate
  DSN. It returned six entries, 21 records, six expected typed errors, entry hash
  `5b77b4a4...c58293`, and the exact frozen summary SHA-256 `a88b44fa...e80b5`. Candidate target and
  bounded landing state matched before and after; provider calls were zero.
- The checkpoint tool revalidated all six prepared source members before/after dump and after the
  restore drill. It captured an atomic PostgreSQL custom archive only after the exact C2_0004
  candidate and Accepted S2B gate passed. Pre/post snapshots contain the exact 26 user/revision
  tables, normalized schema SHA-256 `7237483f...f4aef`, logical SHA-256 `6328e811...054e8`, the
  15/6/6/21/6 landing counts, all required status/lineage/error aggregates, eleven zero integrity
  violations, and zero non-landing business rows.
- Checkpoint manifest SHA-256 is `ab091aac1cfbf2ba1699f521b9a5629d4d9b02dfb236e0600a4f711219c966b1`.
  It binds full commit `cef42a1e075d30c5a0e179f34ab543b4878edabd`, current Git status/diff,
  S4D/S4E tool/test hashes, OpenSpec tree, accepted threshold/corpus hashes, S2B gate, matrix/fresh
  execution, candidate identity, tool versions, sanitized commands, dump hash/list, and complete
  snapshot. No DSN/credential appears in committed evidence.
- Independent restore used candidate image
  `sha256:8ed3192326bb9d114cd5ef9acace453d5dae17425bd089d089330584c84c5a34`,
  a new name/database, network-none, no ports, restart-no, read-only rootfs, tmpfs PGDATA, no Docker
  volume, and a host-bounded Unix socket. PID 1 had exec'd `postgres` and three readiness probes were
  stable before the marker or restore write. Source/restore system IDs are
  `7661313446684311592`/`7661394091808735279`; revision/schema/all table hashes/logical hash match
  exactly. Restore verification SHA-256 is
  `caf789ae87dc4c0429e068dcc3421c8d1346bec02296f6d056d816a3416f0acc`.
- Cleanup first re-proved the returned 64-character owned container ID, stopped PostgreSQL
  gracefully, removed only that ID without force, and proved container/socket absence. Docker
  volume-set hashes before/after match. The external root
  `/md1/mirothinker-backups/canonical-v2-s4-landing-20260711T215953Z-cef42a1` is frozen with 0550
  directories/0440 files and tree SHA-256 `4ae5f2ce...b05012`; repository copies are byte-identical.
- Expanded verification passed: default Canonical V2 `73 passed, 33 explicit skips, 4 expected
  xfails`; a second fresh isolated disposable PostgreSQL target passed `35` migration/integrity/
  landing tests and was removed with unchanged Docker volumes; S1 was `10 passed, 5 explicit skips`;
  S2/S2B was `32 passed`. The four expected xfails remain the approved future KnowledgeBuild,
  KnowledgeRead, KnowledgeAnswer, and ReleasePublication RED interfaces.
- The response-family acceptance uses complementary evidence: Task 4.2's complete
  `newly_collected_response` adapter contract and Task 4.4's real degraded
  `recorded_collected_response` bytes. Known URL/body survive, unknown HTTP metadata remains typed
  missing provenance, and no live call or invented value is needed to accept the family.
- Acceptance record SHA-256 is `20e11fbe2506a44913e58351ef27121065c0b63bfa12a85cdf9425db6578f58c`.
  Tasks 4.1–4.5 and all five Evidence Landing acceptance checks are Accepted. Task 5.1 has not
  started; no canonical/domain/release/index/provider or production-like state was created.
- Final read-only invariants at `2026-07-11T22:14:20Z` re-proved Accepted/50; original `pgtest`
  `paused=true` on exact volume `d81c6381...d241`; original/restore Milvus hashes both
  `43ef203e...67cc`; original/restore FPI salvage hashes both `cef8eb6b...bb7`; recovery and candidate
  network-none/no-port isolation; exact candidate marker/system/C2_0004/bounded counts; and zero
  non-landing rows. No original Postgres command or Milvus client was used.

## S5A task 5.1 assertion/decision RED — 2026-07-11T22:58:11Z

- Three independent read-only design reviews converged on a package-internal deep module,
  `CanonicalDecisionEngine.decide(batch) -> result`, rather than extending `CandidateRelease`,
  adding decision CRUD to `KnowledgeBuild`, or testing direct C2 tables. The future Task 7.2
  `KnowledgeBuild` hides this module; Task 5.1 neither creates nor awakens that public seam.
- Five independent scenarios freeze observable outcomes: all competing field assertions remain
  distinct while a decision-backed current value retains supporting/conflicting evidence; identity,
  source-state, field/entity, and build-as-of constraints filter LLM candidates without deleting
  assertions; recorded structured output is schema/version/evidence/content-hash bound and order-
  independent; material field ambiguity remains unresolved with no current fact; and accepted plus
  unresolved relationship decisions retain all evidence while only accepted relations become
  current.
- The first formal review found three Important contract defects: any nested `ModuleNotFoundError`
  could be masked as expected RED, the four Task 5.2 shared-contract/storage reconciliations were not
  explicit, and unresolved relationship no-projection behavior lacked execution coverage. Exact
  exception-name guarding, an explicit GREEN handoff, and an accepted/unresolved relation pair
  closed them.
- The second review found that an unbound `preferred_source_systems` input could change a winner
  without changing the policy digest, and that arbitrary output hashes were not content-bound. The
  source-preference shortcut was removed; conflicting winner selection now uses recorded structured
  adjudication. Recorded responses now retain canonical raw bytes plus their computed expected
  SHA-256, the trace exposes the validated output and computed digest, and a mismatched digest must
  raise `AdjudicationIntegrityError`. Final independent review reported zero Critical/Important
  findings and Ready.
- Focused normal pytest exited `0` with exactly `5 xfailed`. Final forced
  `--no-cov --runxfail` exited `1` with exactly `5 failed`, every failure the exact absent
  `src.data_agents.canonical_v2.canonical_decision_engine`; there was no syntax, collection,
  fixture, assertion, or nested-import failure.
- One intermediate attempt ran normal and forced pytest concurrently in one worktree. Both
  `pytest-cov` processes targeted shared coverage state; the forced process ended with a coverage
  SQLite `no such table: file` internal error after its five intended failures. The exact empty
  generated shard was removed, serial `--no-cov` replay produced the required five failures, and no
  source/test behavior was changed. Same-worktree pytest verification is serial from this point.
- Default Canonical V2 regression, with all four explicit integration settings removed, was
  `73 passed, 33 explicit skips, 9 expected xfails`: the existing four future deep-module xfails plus
  these five Task 5.1 cases. S1 target/seed-loader safety was `10 passed, 5 explicit skips`; S2/S2B
  was `32 passed`. Ruff check/format, Pyright, strict OpenSpec, and `git diff --check` passed.
- Formal S2B gate returned `state=accepted`, `source_count=50`, manifest
  `a14c1eab...e59c8`, and restore verification `98826e8d...d231`. `pgtest` remained
  `paused=true` on exact volume `d81c6381...d241`; it was not entered or connected. Recovery and
  candidate containers remained running with network none and no ports; candidate restart policy
  remained `no`.
- Hash-only checks matched original/backup Milvus at `43ef203e...67cc` and original/backup FPI
  salvage at `cef8eb6b...bb7`; no Milvus client opened the original. The S4 external checkpoint
  remained directory mode 0550 and file mode 0440.
- Corrected read-only candidate probes returned C2_0004, landing counts `15/6/6/21/6`, canonical
  counts `0/0/0/0/0`, and release/build/active counts `0/0/0`. Two preceding read-only probes used
  incorrect unqualified/schema relation names and failed without mutation before this exact query.
- Task 5.1 is Accepted under the user's objective-verification self-approval authorization. This
  accepts only the RED contract. No production/shared-contract/migration/database/source/index/
  provider/runtime change or write occurred; Canonical knowledge acceptance and S5 overall remain
  open.

## S5B task 5.2 canonical decision GREEN — 2026-07-12T04:32:46Z

- The Accepted Task 5.1 scenarios were implemented behind one package-internal
  `CanonicalDecisionEngine.decide` seam. Every supplied field/relationship assertion is retained;
  deterministic source state, canonical ownership, entity/type/version/path, source-record, and
  build-as-of constraints run before any recorded structured adjudication. Zero survivors and
  material ambiguity remain explicit unresolved decisions with no current projection.
- Recorded LLM output is strict UTF-8/finite JSON with exact base64/raw-byte SHA-256 binding,
  validated-output equality, ordered input evidence, provider/model/prompt/schema versions, and
  disjoint selected/conflicting roles. Selected fields must strictly equal their retained assertion
  values; accepted relationships retain exact typed endpoints and role bindings.
- Decision-group manifests partition every retained assertion and bind complete assertion models.
  Field and relationship IDs now recompute a canonical seed over every serialized decision field,
  policy/method/run/time/trace content, exact deterministic outcomes, the manifest, and identity
  constraint input. Rehashed trace metadata, falsified rejection reasons, wrong canonical owners,
  and reversed relationship endpoints all fail typed result validation.
- C2_0005 hardens all three structured-decision trace families, adds partial unique terminal-role
  indexes, and adds two exact five-column append-only constraint-outcome ledgers. It also adds
  FK-linked append-only field/relationship decision-time identity-context snapshot ledgers. Upgrade
  refuses a populated C2_0004 field or relationship decision table with SQLSTATE `55000` because no
  safe historical context backfill exists; failed upgrades preserve C2_0004 and the original rows.
  Downgrade takes `ACCESS EXCLUSIVE` locks across outcome/context ledgers and refuses any nonempty
  append-only history before dropping C2_0005 objects.
- The explicit-target PostgreSQL store revalidates the Accepted S2B gate, connected database marker,
  disposable kind, and minimum known revision before use. Under one transaction/advisory lock it
  validates current authoritative `identity_decision_output` and source-membership/record context,
  persists assertions, decisions, immutable context snapshots, roles, and outcomes, reconstructs the
  uncommitted typed result, and commits only on exact equality. Exact replay is idempotent; changed
  run content conflicts; missing parents/membership create nothing; no current projection table is
  materialized.
- One merged Task 5.2 review initially found incomplete seed reconstruction and absent
  source-to-canonical ownership checks. Vertical RED/GREEN repairs added complete seed recomputation,
  deterministic outcome replay, field/relationship ownership matrices, and durable mapping
  preflight. Closure then found that loading from mutable current identity state would break old
  decisions after incremental collection. Immutable decision-time snapshots plus
  `persist -> append source record/update allowed source state -> exact historical load` closed that
  defect. The final migration closure added populated-C2_0004 refusal for both decision families.
  Final reviewer disposition: `APPROVED`, zero open Critical/Important findings.
- Commit-checkpoint verification passed:
  - default Canonical V2: `93 passed, 48 explicit integration skips, 4 approved xfails`;
  - real disposable baseline/integrity/decision: `41 passed`;
  - separate S4C landing compatibility: `10 passed`;
  - decision-engine contract: `11 passed`;
  - S1 target plus backup-gate safety and S2/S2B: `49 passed` (`17 + 32`);
  - S4 checkpoint harness: `23 passed`;
  - Ruff check/format, Pyright (`0 errors, 0 warnings, 0 informations`), strict OpenSpec, wheel
    contents, secret scan, and `git diff --check` all passed.
- The real test system was container
  `b748e6b66ac9b3ae2c39d2c25747b7b03072d13d5673784e5ca81ad9e67a7ac3`, network `none`, no
  ports, restart `no`, read-only rootfs, tmpfs PGDATA, system ID `7661462653419962415`, with exact
  disposable database markers. Fresh C2_0005 snapshot and S4C databases ended at zero business rows;
  no sibling database remained. The container was gracefully stopped/removed, its host socket and
  wheel-check roots were deleted, and the Docker volume-set hash remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Final source/candidate audit re-proved Accepted S2B `accepted/50`, original `pgtest`
  `paused=true` on volume `d81c6381…d241`, original Milvus hash-only
  `43ef203e…67cc`, S4 manifest/restore/acceptance hashes, and the exact C2_0004 candidate marker,
  system ID `7661313446684311592`, landing counts, and zero knowledge/publish rows. No original
  Postgres exec/connection or Milvus client was used.
- The audit corrected an earlier shorthand: the durable candidate has no persistent database/role
  `default_transaction_read_only` setting and its unforced value is `off`. All Task 5.2 candidate
  probes explicitly forced read-only sessions/transactions, the decision store rejects non-
  `disposable` targets, and candidate revision/counts remained unchanged. Task 5.2 therefore claims
  zero candidate writes, not database-level immutable enforcement; persistent candidate hardening is
  a pre-existing operational risk for a future authorized infrastructure slice.
- Task 5.2 is Accepted. Task 5.3 identity RED has not started; no canonical candidate release,
  domain projection, index, provider call, legacy `chat.py`, or production-like cutover is claimed.

## Task 5.2 pattern-fix report

- Reported cases fixed: trace/role content gaps, outcome/group relinking, incomplete decision seed
  validation, field/relationship ownership rebinding, historical context drift, unsafe populated
  migration, and ConfigParser percent interpolation across Alembic test targets.
- Defect class: evidence identities were locally typed but not completely content-bound across
  result reconstruction, mutable identity context, persistence, and migration/replay boundaries.
- Sibling search: all three decision trace families, both assertion/decision families, every
  terminal role/outcome ledger, identity source/output mappings, source-record evolution, all
  Alembic URL setters, migration upgrade/downgrade/race paths, and restart/replay behavior.
- Sibling issues found/fixed: one canonical decision seed helper; deterministic constraint replay;
  batch identity contexts; authoritative pre-write mapping checks; immutable per-family context
  snapshots; two-family populated-upgrade refusal; one percent-escaping configuration boundary.
- Not fixed: offline merge/split identity decisions, temporal intervals, typed domain projections,
  publication, and query institution slots belong to Tasks 5.3–S8. Persistent read-only enforcement
  for the already accepted candidate is recorded but was not mutated in this forbidden-write slice.
- New invariant/helper/contract/test: manifest-bound full seeds, exact deterministic outcomes,
  context-snapshot ledgers, historical-load-after-identity-evolution, membership omission matrices,
  SQLSTATE `55000` two-family preflight, minimum-revision lineage, and rendered-socket URL matrices.
- Remaining systemic risk: Task 5.3 must define reversible identity action context for general
  merge/split outputs; future candidate-writing slices must explicitly decide and verify persistent
  candidate access control before broadening authorized writers.

## Task 5.3 canonical identity-resolution RED acceptance — 2026-07-12

- Slice `s5c-canonical-identity-red` used only the approved OpenSpec and slice contract as plan
  sources. No production/shared-contract/migration/database/provider/index/runtime file or state was
  changed.
- Five scenarios cross one future package-internal
  `canonical_identity_resolution` request/result seam:
  - matching normalized DOI evidence merges two prior Paper identities deterministically and
    order-independently;
  - bilingual/cross-format Professor evidence uses an exact-input, raw-byte-bound recorded
    structured-LLM verdict and rejects changed evidence;
  - same-name Professors with conflicting ORCID/institution evidence remain two active objects under
    `different_entities`, with no terminal reject or LLM override;
  - a named mistaken Company merge is reversed once into an exact disjoint/exhaustive 1-to-N source
    allocation while prior identities/decisions remain history;
  - recovered WAL/FPI Patent evidence links to an existing official canonical identity while the
    V042 ID, source system/key, records, assertions, and mapping lineage remain retained.
- One shared invariant proves unique active source ownership, no missing/duplicate/cross-wired
  assignments, source-to-decision-to-output consistency, active/history separation, exact
  source/record/assertion retention, request policy/run/method binding, output decision linkage, one
  release-scoped manifest per decision, and mutation-sensitive decision/result hashes. Candidate
  verdicts stay independent from applied actions; only direct `same_entity` actions inherit the
  verdict confidence/rationale/trace.
- The intentional RED marker catches only a private sentinel emitted for the exact absent target
  module. A nested or lazy `ModuleNotFoundError` after import is not an accepted xfail.
- Focused verification:
  - `uv run pytest -n0 tests/canonical_v2/test_canonical_identity_resolution_contract.py -q
    --tb=short` -> exactly `5 xfailed`;
  - the same command with `--no-cov --runxfail` -> exactly five failures, each
    `_MissingTargetModule` directly caused by the exact target `ModuleNotFoundError`;
  - focused Ruff check/format and Pyright -> clean, `0 errors, 0 warnings, 0 informations`.
- Commit-checkpoint verification:
  - explicit no-database `uv run pytest -n0 tests/canonical_v2 -q --tb=short` -> `93 passed, 48
    skipped, 9 expected xfails`;
  - `test_database_target_safety.py` plus `test_rebuild_write_gate.py` -> `17 passed`;
  - the four S2 harnesses plus S2B backup/restore -> `32 passed`;
  - S4E checkpoint harness -> `23 passed`;
  - formal `backup_restore.py verify-gate` -> `state=accepted`, `source_count=50`, backup manifest
    `a14c1eab…e59c8`, restore verification `98826e8d…7d231`;
  - strict OpenSpec, `git diff --check`, high-confidence secret scan, Ruff check/format, and Pyright
    all passed.
- The single merged specification/code-quality review found and closed assignment completeness and
  cross-wiring, overly broad xfail masking, recovery create-vs-link, decision/result evidence
  binding, and candidate-verdict/action coupling defects. Final disposition: `APPROVED`, zero open
  Critical/Important findings.
- Read-only source/candidate audit:
  - original `pgtest` remains `paused=true` on exact volume `d81c6381…d241`; no exec or connection
    was made against it;
  - original Milvus was hash-only and remains `43ef203e…67cc`; S4 checkpoint/restore/acceptance hashes
    remain `ab091aac…966b1`, `caf789ae…f0acc`, and `20e11fbe…f58c`;
  - durable candidate container remains network-none/no-port/restart-no at exact ID
    `c0bf2374…b21849`. A forced read-only transaction proved the exact isolated-candidate marker,
    revision C2_0004, landing counts `15/6/21/6/6`, and zero rows in all 20 knowledge/publish tables;
  - the candidate's unforced persistent default remains `default_transaction_read_only=off`. Task
    5.3 made no connection without the explicit read-only setting except the read-only `SHOW` probe
    and claims no database-level immutable enforcement.
- Task 5.4 handoff is explicit: current identity tables cannot express output-specific split
  allocation, immutable decision-time identity context, or complete release/assertion-bound
  decision replay. GREEN must add these effects without inferred backfill, preserve unique current
  ownership separately from terminal history, and keep all identity mutation inside the offline
  build. Migration and downgrade safety receive the extra review/testing permitted by lean
  execution.

## S5D task 5.4 canonical identity GREEN — 2026-07-12T08:40:35Z

- The Accepted Task 5.3 pair scenarios now run through one complete-release
  `CanonicalIdentityResolver.resolve(request) -> result` seam. The engine normalizes DOI, ORCID,
  patent, company, and textual keys; recalls deterministic multi-domain components; applies strong-
  identifier, Professor composite, and recorded structured-LLM rules; and materializes stable no-op,
  create, link, merge, split, reverse, reject, or unresolved effects with generation-safe successor
  IDs.
- Candidate verdicts, applied decisions, manifests, exact decision-time contexts, output-specific
  source allocations, active current owners, terminal history, and lineage remain independently
  content-bound. Pair/component LLM evidence is never copied onto unrelated local decisions;
  contradictory groups, confidence below the versioned threshold, tampered raw bytes, changed
  assignments, unknown lineage, entity conflicts, and rehashed action/output substitutions fail
  validation or degrade without terminally rejecting valid objects.
- C2_0006 adds immutable identity-resolution runs, candidate verdicts, complete context snapshots,
  assertion/source/record edges, output membership, current assignments, and lifecycle lineage.
  Deferred PostgreSQL validators enforce action cardinality, exact non-reject source partitions,
  context/evidence/LLM-edge equality, active-membership/current-assignment equality, canonical state,
  and lineage topology. All identity tables are locked in one parent-to-child order by the store,
  upgrade, and downgrade; downgrade refuses nonempty append-only history with SQLSTATE `55000`.
- The explicit PostgreSQL adapter rechecks the Accepted backup gate and connected disposable marker
  before its first write, locks the full projection, compares existing source rows, complete record
  sets, and assertion fingerprints before inserting a run, persists atomically, forces deferred
  constraints before commit, and reloads the exact typed snapshot. Same-ID/different-content,
  missing parents, row-key substitution, late rollback, and concurrent replay leave no partial
  identity rows. The C2_0005 decision store retains its legacy path but rejects multi-output
  decision-wide ownership rather than inferring an unsafe source mapping.
- One merged specification/code-quality review reported one Critical and five Important findings;
  the vertical repair loop closed complete-batch resolution, prior-context binding, action/output
  hashes, decision-local evidence, exact base-row conflict checks, and deep-module exports. The one
  focused migration/database-safety review reported five Important and one Minor finding; closure
  added deferred release/action validators, exact relational release checks, full parent-first
  writer/downgrade locks, store-vs-downgrade race coverage, tolerant in-development downgrade, and
  lock/trigger inventory assertions. Closure audit found zero open Critical/Important findings; no
  second merged review was performed under lean execution.
- Commit-checkpoint verification passed:
  - focused identity/decision/head matrix: `75 passed` (`29` pure identity, `32` identity Postgres,
    `13` C2_0005 decision compatibility, `1` head inventory);
  - explicit no-database Canonical V2: `124 passed, 79 explicit integration skips, 4 approved
    future-interface xfails`;
  - real S5D disposable Canonical V2 excluding the separately named S4C module: `193 passed, 4
    approved xfails`; independent S4C landing compatibility: `10 passed`;
  - S1 target plus gate safety: `17 passed`; four S2 harnesses plus S2B: `32 passed`; S4E checkpoint:
    `23 passed`;
  - Ruff check/format, targeted Pyright (`0 errors, 0 warnings, 0 informations`), strict OpenSpec,
    formal verification-contract gate, wheel contents, cached diff, high-confidence secret scan,
    and writer-import isolation all passed. The wheel contains C2_0001–C2_0006 and both canonical
    identity modules.
- One initial all-in-one integration invocation produced nine setup errors because the frozen S4C
  test correctly rejected the S5D expected database name. No behavior assertion failed. Running the
  suite on its two explicitly named, independently marked disposable bases produced the passing
  `193 + 10` results above; the safety rejection was not weakened.
- Formal S2B admission remains `state=accepted`, `source_count=50`, backup manifest
  `a14c1eab…e59c8`, and independent restore verification `98826e8d…7d231`. Docker metadata shows
  original `pgtest` still `paused=true` on exact volume `d81c6381…d241`; it was neither entered nor
  connected. Recovery and durable-candidate containers remain network-none/no-port/restart-no.
  SHA-256 hash-only checks matched original/restored Milvus at `43ef203e…67cc` and original/restored
  FPI salvage at `cef8eb6b…bb7`; no Milvus client opened the original.
- A forced read-only candidate transaction re-proved exact isolated-candidate marker, PostgreSQL
  system ID `7661313446684311592`, revision C2_0004, landing counts `15/6/6/21/6`, and zero rows
  across all 20 knowledge/publish tables. S4 manifest, restore, and acceptance hashes remain
  `ab091aac…966b1`, `caf789ae…f0acc`, and `20e11fbe…f58c`.
- The real disposable was container `ef1768e1df66b3a119ba93f975171f045ef2fb99bbee27ddd11f09c4f2c6b501`,
  network `none`, no ports, restart `no`, read-only rootfs, tmpfs PGDATA, PostgreSQL system ID
  `7661462653419962415`, with exact disposable markers. Its S5D and S4C bases ended at C2_0006 with
  zero business rows and no test sibling database. The container, host socket, and wheel artifacts
  were removed; Docker volume-set SHA-256 remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Task 5.4 is Accepted under the existing objective-verification authorization. Task 5.5 has not
  started; no durable-candidate migration, original/recovery write, domain projection, release,
  publication, Milvus rebuild, provider call, query/chat behavior, or cutover is claimed.

## Task 5.4 pattern-fix report

- Reported cases fixed: pair-only identity resolution, content-rehash bypasses, decision-wide split
  ownership, missing decision-time context, unsafe same-ID replay, incomplete cross-row constraints,
  and migration/store lock races.
- Defect class: identity effects were locally typed but not completely bound across release-batch
  planning, immutable evidence context, relational projection, current ownership, lifecycle history,
  and concurrent migration boundaries.
- Sibling patterns searched: every action and entity domain; candidate verdict and structured-LLM
  trace paths; source/assertion/record identity; current and terminal mappings; store/load/replay;
  upgrade/downgrade/preflight; C2_0005 ownership compatibility; and query/admin/runtime writer use.
- Sibling issues found/fixed: one release-batch engine and rule-set hash; explicit prior decision
  contexts; per-output allocation; complete base-row comparison; deferred action/release validators;
  one shared parent-first lock order; and fail-closed legacy multi-output ownership.
- Not fixed: temporal intervals, review queues, typed domain projections, eligibility, publication,
  query institution slots, Web augmentation, answer generation, and index work belong to Tasks 5.5+
  and S6–S10.
- New invariant/helper/contract/test: complete context hashes, generation-safe identity IDs, exact
  decision/output binding, multi-component four-domain matrix, create→merge→reverse round-trip,
  low-confidence degradation, relational topology validators, conflict-before-run tests, and real
  store/downgrade serialization.
- Remaining systemic risk: future temporal and aggregate S5 work must preserve these immutable
  decision-time contexts while adding validity/current-history projections; the durable candidate
  remains deliberately behind at C2_0004 until a later explicitly authorized candidate write.

## Explicit non-claims

- S2B acceptance satisfies only the backup prerequisite; each later task still requires its own
  Ready slice, explicit isolated target, and verification loop.
- No populated Canonical V2 candidate, serving projection, or Milvus release is accepted.
- Task 5.3 does not claim Task 5.4 implementation, durable identity storage, or S5 acceptance.
- No original source write or production-like cutover is authorized.

## S5E task 5.5 proportional temporal semantics — 2026-07-12T09:58:35Z

- `CanonicalDecisionEngine.decide` remains the one deep decision seam. Assertions retain
  `observed_at`, optional source publication/event time, and optional natural validity. Selected
  evidence must share one exact interval; equal values/attributes with different intervals remain
  unresolved unless a structured adjudicator selects one exact interval-bound subset.
- Validity membership is half-open `[valid_from, valid_to)`. Field and relationship decisions
  outside their interval remain immutable history while only the as-of-valid subset appears in
  generic current selections. Null endpoints remain open/unknown and are never synthesized;
  `source_event_time` neither replaces `observed_at <= as_of` nor creates validity.
- A Professor A→B affiliation-like scenario retains both generic relationship episodes and their
  evidence, copies exact selected validity into relationship decisions/current selections, treats
  the shared boundary correctly, and returns only B as current. Active, ended-at-boundary, future,
  unknown-validity, static-field, overlapping-conflict, reordered replay, and rehashed tamper cases
  are covered for both field and relationship families.
- All Canonical V2 aware timestamps now use one `CanonicalDatetime` contract that normalizes the
  instant to UTC before JSON, IDs, hashes, fingerprints, or persistence. UTC and `+08:00` inputs
  produce byte-identical results; a real PostgreSQL restart under an `Asia/Shanghai` session proves
  session timezone cannot change durable hashes.
- Validation-time selected-interval disagreement now raises `ValueError`, which Pydantic and the
  PostgreSQL adapter can translate. Generation maps an invalid structured selection to
  `AdjudicationOutputError`; corrupt durable restart remains wrapped as
  `CanonicalDecisionPersistenceError` rather than leaking an engine-private exception.
- No C2_0007 migration was added. C2_0002 and C2_0005 already retain assertion observation/event/
  validity and relationship-decision validity; field current validity is derived from immutable
  selected assertions, avoiding a duplicate temporal store.
- Focused evidence:
  - `test_shared_contracts.py` plus `test_canonical_decision_engine_contract.py` -> `39 passed`;
  - complete `test_canonical_decision_postgres.py` on the named disposable -> `16 passed`;
  - targeted Ruff format/check -> clean; targeted Pyright -> `0 errors, 0 warnings, 0
    informations`.
- Commit-checkpoint regression:
  - explicit no-database Canonical V2 -> `136 passed, 82 skipped, 4 approved xfails`;
  - real S5E disposable Canonical V2 excluding the fixed-name S4C module -> `208 passed, 4 approved
    xfails`;
  - independent fixed-name S4C PostgreSQL compatibility -> `10 passed`;
  - S1 target plus write-gate safety -> `17 passed`; four S2 harnesses plus S2B -> `32 passed`; S4E
    checkpoint harness -> `23 passed`;
  - formal S2B gate -> `state=accepted`, `source_count=50`, backup manifest
    `a14c1eab…e59c8`, restore verification `98826e8d…7d231`;
  - wheel contents include C2_0001–C2_0006, shared contracts, decision engine/store, and identity
    engine/store; strict OpenSpec, diff/whitespace, high-confidence secret scan, and offline-writer
    import isolation passed.
- The one merged specification/code-quality review found two Important defects: offset-dependent
  time hashes/restart and an engine-private validation exception. The repair loop closed both plus
  two Minor audit-wording/fixture-semantics findings. Final disposition is `APPROVED`, with zero open
  Critical/Important findings. Relationship `superseded` interval semantics and projector
  deduplication remain non-blocking Task 5.6/deepening follow-ups.
- Frozen-source/candidate audit:
  - original `pgtest` remains `paused=true` on exact volume
    `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`;
  - original Milvus hash-only check remains `43ef203e…67cc`; verified FPI salvage remains
    `cef8eb6b…bb7`; the initial worktree-relative Milvus path was absent, then the exact frozen
    source path `/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db` matched;
  - recovery lab and durable candidate remain network-none/no-port/restart-no. A forced read-only
    candidate transaction re-proved exact marker, system ID `7661313446684311592`, C2_0004, landing
    `15/6/6/21/6`, and zero rows in all 20 knowledge/publish tables;
  - S4 manifest/restore/acceptance hashes remain `ab091aac…966b1`, `caf789ae…f0acc`, and
    `20e11fbe…f58c`.
- Owned disposable container
  `75195921959bd8f4252cc363fdc447bfdc24c2134eb438b39167934e25c94ce9` used system ID
  `7661567410199961641`, network `none`, no ports, restart `no`, read-only rootfs, tmpfs PGDATA, and
  exact disposable markers. Its S5E/S4C bases ended at C2_0006 with zero business rows and no test
  sibling database. Container, socket root, databases, and wheel-check artifacts were removed;
  Docker volume-set SHA-256 remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Task 5.5 is Accepted. Task 5.6 production work did not start in this commit; no durable-candidate
  migration, original/recovery write, Milvus open/rebuild, live provider call, domain projection,
  publication, query/chat change, push, PR, or cutover is claimed.

## Task 5.5 pattern-fix report

- Reported cases fixed: historical/future decisions incorrectly projected as current, exact
  intervals dropped on restart, equal interval-conflicting evidence auto-merged, non-UTC instants
  changed hashes, and validation corruption leaked a private exception.
- Defect class: temporal meaning was retained in row fields but not treated as one canonical,
  hash-stable invariant across decision generation, current projection, model validation, and
  restart reconstruction.
- Sibling patterns searched: every `AwareDatetime` in the shared Canonical V2 contract and engine;
  field and relationship deterministic/LLM paths; selected/current validation; assertion
  fingerprints; PostgreSQL write/load/replay; timezone session behavior; and query/runtime writer
  imports.
- Sibling issues found/fixed: one UTC-normalized timestamp type across all shared contract fields;
  UTC-normalized batch/current fields; one exact-validity primitive; typed generation translation;
  both field/relationship current subsets; faithful validity-interval fixture metadata; and corrupt
  restart wrapping.
- Not fixed and why: `superseded` relationship interval shape is not emitted or specified by Task
  5.5 and belongs to Task 5.6; consolidating the adapter projector is a non-blocking future deepening
  because shared primitives plus result validation already fail closed.
- New invariant/helper/contract/test: `CanonicalDatetime`, `_selected_validity`,
  `_generated_selected_validity`, `_interval_contains`, affiliation transition/membership matrices,
  offset-equivalence hashing, Asia/Shanghai restart, tamper cases, and corruption abstraction.
- Remaining systemic risk: Task 5.6 must freeze review/supersession history before S6 assigns typed
  relationship time semantics; the durable candidate deliberately remains C2_0004 until a later
  explicitly authorized candidate write.

## S5F task 5.6 review/history acceptance — 2026-07-12T15:04:36Z

- Unresolved field, relationship, and identity outcomes now expose deterministic immutable
  `ReviewCase` values bound to the originating decision/verdict, exact candidates and conflicts,
  policy/method/confidence, and evidence. An admissible `HumanReviewResolution` binds reviewer,
  review policy/version, outcome, rationale, reviewed time, and exact selected/rejected evidence;
  it produces a new offline `human_review` decision or verdict and never mutates prior history.
- Field review can select only one exact equal-value/validity set or reject all evidence;
  relationship review requires exact endpoints/type/version/roles and one exact validity set;
  identity review preserves exact output-specific source groups for create/link/merge/split/reverse/
  reject. Stale, unsupported, cross-wired, future, or invented resolutions fail closed.
- `DecisionHistoryProjection` retains all assertions, decisions, and review cases across the linear
  release ancestry while deriving only the unique as-of-valid unsuperseded lineage head as current.
  Ordinary replacement, explicit withdrawal, unresolved/rejected, future/ended, and accepted heads
  reconstruct identically from memory and PostgreSQL restart; an inactive latest head never revives
  an older head.
- C2_0007 retains immutable human-review provenance and hardens decision lineage at both the adapter
  and direct-SQL boundaries. Migration preflight and triggers reject release/decision cycles,
  duplicate logical roots, child forks, non-ancestral or same-release supersession, field-subject
  drift, and relationship ID/type/version/endpoint drift. Partial unique root indexes plus global
  predecessor uniqueness close concurrent forks; downgrade removes the new boundary symmetrically
  under the parent-first lock and refuses retained review provenance.
- Checkpoint regression on the final code state:
  - explicit no-database Canonical V2 -> `145 passed, 107 skipped, 4 approved xfails`;
  - real marked disposable Canonical V2 excluding fixed-name S4C -> `242 passed, 4 approved xfails`;
  - independent fixed-name S4C PostgreSQL compatibility -> `10 passed`;
  - focused final decision engine/PostgreSQL matrix -> `66 passed`;
  - S1 target plus write-gate safety -> `17 passed`; S2/S2B harnesses -> `32 passed`; S4E
    checkpoint harness -> `23 passed`;
  - formal S2B gate -> `state=accepted`, `source_count=50`, backup manifest
    `a14c1eab…e59c8`, restore verification `98826e8d…7d231`;
  - a fresh empty marked database upgraded through C2_0001–C2_0007; the real suite's migration
    preflight, downgrade/re-upgrade, retained-data refusal, direct-SQL, restart, rollback, and
    concurrency scenarios all passed.
- Ruff check/format passed for all Task 5.6 Python files; targeted Pyright returned `0 errors, 0
  warnings, 0 informations`. The wheel contains C2_0001–C2_0007 plus the shared contracts,
  decision/history engine/store, identity engine/store, and landing module. Strict OpenSpec,
  `git diff --check`, the formal verification-contract gate, high-confidence secret scan, and
  offline-writer import isolation passed.
- The single merged specification/code-quality review and the focused migration/write-boundary
  safety review both ended with zero open Critical or Important findings. Repairs covered exact
  previous-history binding, engine-owned replacement/withdrawal, all three review families,
  grouped identity source allocation, stale branches, concurrent duplicate roots, direct-SQL
  ancestry/metadata enforcement, cycle-safe migration preflight, and symmetric downgrade cleanup.
- Frozen-source/candidate audit:
  - formal S2B remains accepted for 50 sources; acceptance hash is `3155d890…739fc5b`;
  - original `pgtest` remains paused on exact volume
    `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; it was inspected only
    through Docker metadata and was never exec'd or connected;
  - original/restore Milvus hashes remain `43ef203e…67cc`, and original/restore FPI salvage hashes
    remain `cef8eb6b…bb7`; no Milvus client opened the original;
  - recovery lab and durable candidate remain network-none/no-port/restart-no. A forced read-only,
    serializable, deferrable candidate transaction re-proved the exact isolated-candidate marker,
    system ID `7661313446684311592`, C2_0004, landing artifact/run/parser/record/error counts
    `15/6/6/21/6`, and zero rows in all 20 knowledge/publish tables, then rolled back;
  - S4 manifest/restore/acceptance hashes remain `ab091aac…966b1`, `caf789ae…f0acc`, and
    `20e11fbe…f58c`.
- Owned disposable container `b7476c77f828…744e19` used system ID `7661598327849119792`, network
  `none`, no ports, restart `no`, read-only rootfs, tmpfs PGDATA, and exact disposable markers. All
  six Task 5.6 test databases, the container, socket root, and wheel-check directory were removed;
  Docker volume-set SHA-256 remained
  `8314a2b0200baffdf78d25ebfe0a9f11c5b22f129f8f33c05f1aa4f859ec896c`.
- Task 5.6 and aggregate S5 are Accepted. Task 6.1 has not started. No durable-candidate migration,
  original/recovery write, Milvus open/rebuild, live provider call, typed domain projection,
  publication, query/chat change, push, PR, or cutover is claimed.

## Task 5.6 pattern-fix report

- Reported cases fixed: unresolved decisions lacked one durable review contract; human outcomes
  could not be bound to exact prior evidence; latest-head replacement/withdrawal was incomplete;
  identity review allocation and direct-SQL supersession safety were not closed end to end.
- Defect class: append-only records existed, but review provenance and lineage-head semantics were
  not one shared invariant across Pydantic contracts, the two deep engines, persistence adapters,
  migration preflight, database constraints/triggers, restart reconstruction, and current views.
- Sibling patterns searched: field, relationship, and identity review families; deterministic and
  recorded-LLM decisions; create/link/merge/split/reverse/reject; replacement/withdrawal/unresolved/
  rejected/future/ended heads; UTC hashes; adapter/direct-SQL writes; populated upgrade/downgrade;
  release and decision cycles; root/fork races; and query/runtime writer imports.
- Sibling issues found/fixed: one typed review-case/resolution family, exact predecessor-history
  validation, engine-owned transitions, grouped identity source allocation, one generic history
  projection, strict root/child/ancestry/subject invariants, migration preflight, direct-write
  triggers, concurrent unique indexes, restart parity, and rollback/refusal tests.
- Not fixed and why: reviewer authorization/signatures, mutable claim/lock/SLA/priority state, Admin
  UI, and incomplete-case transfer are explicitly S10 concerns; typed domain/relationship catalogs
  and projections remain S6; branching release graphs are outside the approved linear-history
  contract.
- New invariant/helper/contract/test: `ReviewCase`, `HumanReviewResolution`, explicit decision
  transitions, `DecisionHistoryProjection`, exact-head store admission, C2_0007 lineage validators,
  three-family review matrices, grouped identity restart, root/fork concurrency, direct-SQL and
  populated-migration refusal coverage.
- Remaining systemic risk: S6 must consume the accepted generic history without weakening evidence
  or lineage semantics, and S10 must add operational review state without converting immutable cases
  or resolutions into mutable canonical truth.

## S6A task 6.1 PRD domain/relationship catalog acceptance — 2026-07-12T16:40:08Z

- Four vertical TDD increments froze exact source/citation identity, typed four-domain fields and
  sub-objects, seven relationship families plus three layer boundaries, and complete type/family/
  direction scenario accounting. Observed REDs included a missing validator, empty domain and
  relationship ledgers, missing scenario references/content hash, accepted schema drift, uniform
  relationship states, unsupported alias semantics, broad type citations, wrong role ownership,
  unconstrained union endpoints, unsafe builder output, and the stricter app-environment Pyright
  failures. Each RED failed for the intended missing/broken contract before its GREEN.
- The frozen catalog binds 14 repository-confined authority files and 27 exact citation ranges/
  source-term checks. It contains 9 shared projection fields, 101 Professor/Company/Paper/Patent
  fields, 28 typed sub-objects with explicit parents, 7 canonical relationship families, 34 exact
  `RelationshipType` rows, 42 accounting scenarios, 8 approved traversal directions, and 5 deferred
  owners. Catalog content SHA-256 is `c7730380…08d2`; checked-in file SHA-256 is
  `e0c72585…55e3`.
- Locked precedence now requires Paper `venue` and Professor `patent_ids`. Paper summaries remain
  conditional for canonical inclusion and are scoped to the quality-ready policy, avoiding a global
  completeness gate. `quality_status` remains a signal rather than path admission, `last_updated`
  is observation metadata, and `top_papers` remains a deferred release-derived result.
- Identity and evidence lineage rows are immutable, row-bound, and explicitly persistence-deferred
  to Task 6.5. Business facts retain accepted/unresolved/rejected/superseded decision semantics.
  Same-domain identity constraints, decision/assertion family-subject compatibility, exact role
  ownership, Professor-Company role exclusivity, Professor-Paper attribution/evidence separation,
  applicant-not-owner semantics, and conditional Company/Professor endpoint paths fail closed in
  the validator and negative mutation matrix.
- Relationship source accounting reports 2 absent, 7 insufficient-evidence, and 33 supported
  scenarios. `supported` means retained S2 source material exists; none of these labels claims a
  canonical edge, endpoint population, publication, or retrieval admission. Concrete derived types
  remain S7/S8-owned and session types remain S9-owned.
- Builder output is confined to the approved S6 root, rejects symlink/path escapes, validates a
  same-filesystem temporary artifact before atomic replacement, and preserves the prior file on
  validation failure. Strict JSON duplicate/unknown-key, deterministic ordering, source hash/range/
  term, content self-hash, family/type/scenario completeness, role/state/time/path, and deferred-
  owner drift cases are covered.
- The one merged specification/code-quality review initially found five Important issues. The same
  review closed requiredness precedence, role/evidence semantics, endpoint compatibility, atomic
  output safety, and app-environment Pyright, found no Critical/Important regression, and returned
  final `Ready: Yes`.
- Commit-checkpoint evidence on the final implementation state:
  - deterministic `build_domain_catalog.py --check` passed;
  - Task 6.1 catalog plus Accepted shared-contract tests -> `24 passed in 0.62s`;
  - Ruff check -> `All checks passed!`; Ruff format check -> `3 files already formatted`;
  - app-environment Pyright -> `0 errors, 0 warnings, 0 informations`;
  - formal S2B gate -> `state=accepted`, `source_count=50`, backup manifest
    `a14c1eab…e59c8`, restore verification `98826e8d…7d231`;
  - strict OpenSpec -> valid; tracked diff/whitespace, high-confidence secret,
    generated-cache, and final artifact-scope checks -> clean.
- Task 6.1 is Accepted. No production Python/public interface, migration, domain table/model,
  PostgreSQL, Milvus, provider, durable-candidate, runtime/query/chat/admin behavior, push, PR, or
  cutover changed. The original sources and C2_0004 durable candidate were not opened or written.

## Task 6.1 pattern-fix report

- Reported cases fixed: broad relationship-family citations, unsupported canonical alias edge,
  uniform state/binding defaults, generic Company-role bypass, and unconditional union-endpoint
  traversal paths.
- Defect class: L6 evidence/provenance violation plus L4 schema/state contract drift and C1 missing
  sibling matrix. One helper default and broad citations affected identity, organization, scholarly,
  intellectual-property, Company-business, taxonomy, and evidence-lineage siblings.
- Sibling patterns searched: legacy admin relationship/query paths; Accepted canonical identity and
  relationship contracts; all four domain fields/sub-objects; active OpenSpec design/recovery specs;
  authoritative PRD/reviews; S2 typed-business/relationship evidence; and Multi-turn directions.
- Sibling issues found/fixed: exact authority additions, per-row endpoint binding/state/citation,
  role ownership, attribution evidence separation, same-domain/family/subject constraints,
  requiredness scopes, output confinement, parent/observation semantics, and negative drift tests.
- Not fixed and why: production persistence/endpoint representation is Task 6.5; inclusion and typed
  projections are Tasks 6.2–6.3; path admission is Tasks 6.6–6.7; institution slot/query rewriting
  is S8; legacy `chat.py` institution stopwords remain untouched by explicit scope.
- New invariant/helper/contract/test: exact manifest/citation and self-hash validator, deterministic
  catalog builder, row-specific relationship semantics, total scenario/deferred ledgers, atomic
  output guard, shared-contract round-trip, and source/schema/semantic mutation matrices.
- Remaining systemic risk: Task 6.5 must choose executable persistence for metadata/sub-object
  endpoints without falsely routing them through canonical-identity-only decisions, and S8 must
  obtain one accepted release-scoped institution/alias catalog rather than reuse legacy name maps.

## S6B task 6.2 domain-inclusion RED acceptance — 2026-07-12T17:17:06Z

- Five exact-target scenarios freeze the future package-internal
  `DomainInclusionEngine.evaluate(InclusionBatchRequest) -> DomainInclusionResult` seam. They cover
  approved/unapproved Professor seeds, roster-anchored/global-only Papers, approved/unapproved
  Patent exports, Company skeleton and four-dimension incremental admission, incomplete review,
  contrary scope, and query-time Web-only exclusion.
- The request binds four shared `PolicyReference` values, active canonical/source identities,
  retained `EvidenceArtifact`/record/assertion values, Professor discovery anchors, offline Company
  validation decisions, and a deterministic approved-source-scope manifest. Manifest entries bind
  exact batch/artifact/content hashes; evaluation records the manifest hash and rejects an artifact
  hash mismatch.
- Professor admission depends on approved seed membership without a runtime institution-name or
  geography whitelist. Paper discovery evidence is retained separately from Professor authorship.
  Patent export rows remain included despite missing optional type/inventor/IPC/linkage/enrichment.
  Company skeleton records bypass completeness gates; incremental auto-admission requires supported
  basic identity, Shenzhen geography, innovation/business relevance, and source validation, while
  incomplete evidence yields review and contrary scope yields a named exclusion.
- Every admitted, review, and excluded decision is a shared `PolicyDecision`, has `path=None`, binds
  the exact domain policy/release and retained assertions, and appears in one deterministic per-domain
  outcome set. Input reversal is byte/result stable where exercised. Query-time Web evidence remains
  outside canonical inclusion and the request remains unchanged.
- The one merged specification/code-quality review initially found two Important issues: approved
  manifest identity was not observably bound to the result, and non-admitted decisions could lack
  supporting evidence. The same review closed both; final review has zero open Critical/Important
  findings.
- Checkpoint commands and final outcomes:
  - focused normal RED -> exactly `5 xfailed`, exit 0;
  - focused forced RED -> exactly five direct `_MissingTargetModule` failures for
    `src.data_agents.canonical_v2.domain_inclusion`, expected exit 1;
  - Task 6.1 catalog/shared contracts plus Task 6.2 normal RED -> `24 passed, 5 xfailed`;
  - Ruff check -> `All checks passed!`; Ruff format -> `1 file already formatted`;
  - app-environment Pyright -> `0 errors, 0 warnings, 0 informations`;
  - strict OpenSpec -> valid; staged diff/secret/cache/scope checks -> clean.
- This test-only task did not replay database/source/Candidate/Milvus/provider safety totals and did
  not mutate those boundaries. No product/shared-contract/migration/runtime file changed. Task 6.3
  remains the GREEN owner.

## S6F task 6.6 path-eligibility RED acceptance — 2026-07-12T17:22:49Z

- Five strict scenario families freeze the future package-internal
  `PathEligibilityEngine.evaluate(PathEligibilityRequest) -> PathEligibilityResult` seam. Inputs
  explicitly declare future Task 6.3 typed projection/inclusion and Task 6.5 relationship outputs;
  no local fake implements either dependency.
- The published user-path registry is exactly exact lookup, structured filter, verified relationship
  traversal, semantic recall, recommendation, and ranking. Every result has one unique named
  `PolicyDecision` with a path-policy version; internal audit/identity paths are excluded and a
  legacy global-`ready` poison value has no effect.
- Four-domain partial projections remain exactly reachable with visible limitations. Accepted edges
  preserve Task 6.1 canonical source/target orientation while all eight user directions remain
  traversable; incomplete target enrichment is soft. A rejected Professor-Paper attribution blocks
  only traversal while the Paper remains exactly reachable.
- Missing enrichment, partial summaries, ordinary uncertainty, and stale non-material facts never
  become unnamed hard exclusions. Wrong identity, terminal rejection, unsafe exposure, no usable
  source-grounded facts, and broken references are named and evidence-bound. Broken references are
  scoped to dependent traversal; merged predecessors carry no current projection/admitted inclusion
  and resolve through a shared identity decision to one survivor.
- The one merged review initially found five Important defects: canonical lifecycle/Paper status
  conflation, reverse-direction fixtures that inverted canonical edges, global broken-reference
  exclusion, a current projection for a terminal merged predecessor, and rejected attribution
  affecting Paper identity. The same review closed all five; final review has zero open
  Critical/Important findings.
- Final checkpoint commands and outcomes:
  - focused normal RED -> exactly `5 xfailed`, exit 0;
  - focused forced RED -> exactly five direct `_MissingTargetModule` failures for
    `src.data_agents.canonical_v2.path_eligibility`, expected exit 1;
  - Task 6.1 catalog/shared contracts plus Task 6.6 normal RED -> `24 passed, 5 xfailed`;
  - Ruff check -> `All checks passed!`; Ruff format -> `1 file already formatted`;
  - app-environment Pyright -> `0 errors, 0 warnings, 0 informations`;
  - strict OpenSpec and staged diff/secret/cache/scope checks -> clean.
- This test-only task did not replay database/source/Candidate/Milvus/provider safety totals and did
  not mutate those boundaries. No product/shared-contract/migration/runtime file changed.

## S5G task 5.7 temporal-precision correction acceptance — 2026-07-13T09:19:45Z

- Initial pure RED failed collection because `TemporalComparisonContext` and the precision-bearing
  value contract did not exist. The first real-disposable PostgreSQL RED then failed with
  `cannot adapt type 'TemporalDateValue'`, proving the legacy adapter could not persist date-only
  validity without coercion.
- The shared discriminated temporal contract now retains `date` and UTC-canonical `instant` as
  different values. Exact equality and hashes bind precision plus value. Cross-precision comparison
  returns `indeterminate` without context; `explicit-calendar-v1` uses only a caller-supplied named
  Gregorian timezone and reports a date/inside-instant pair as overlap, never equality.
- Assertions, generic current selections, relationship decisions, history projections, and the
  Task 6.3 typed-subobject consumer carry the same precision-bearing value. Date-only affiliation
  evidence reaches the S6 projection seam without UTC-midnight fabrication.
- C2_0008 stores the precision object in JSONB, retains the legacy `timestamptz` mirror only for
  instants, hashes the exact representation, persists explicit comparison context, and reconstructs
  both adapters exactly after restart. Direct SQL constraints reject malformed representation,
  non-accepted relationship validity, inconsistent selected validity, and decision/assertion
  temporal cross-wiring.
- Migration review found two Important risks and closed both. C2_0008 temporarily suspends only the
  owned append-only mutation trigger while rehashing standalone legacy instant assertions, and
  refuses to rewrite already referenced temporal decision evidence. A regression first exposed an
  over-broad table-nonempty preflight; the corrected gate follows actual decision edges, so
  standalone evidence backfills while referenced evidence fails closed.
- Pure GREEN command over temporal/shared/identity/decision contracts: `85 passed`.
- Real network-none/no-port disposable decision-persistence command: `44 passed`; it covers
  C2_0001→C2_0008, two standalone instant backfill/downgrade/re-upgrade cycles, referenced-evidence
  refusal, date downgrade refusal, direct-SQL precision cross-wire rejection, restart, replay,
  history, tamper, transaction, and lock ordering.
- Real network-none/no-port disposable identity-persistence command: `35 passed, 1 deselected`.
  The deselected permanent-single-head assertion is explicitly Task 6.3-owned because its dirty
  C2_0009 descendant is present; all S5 identity behavior including date restart passed.
- Current no-external-database Canonical V2 result: `188 passed, 125 skipped, 9 xfailed, 1 failed`.
  The only failure is that same stale exact-head assertion (`C2_0009` observed versus `C2_0008`
  expected), retained as Task 6.3 RED rather than hidden in the S5G commit.
- Ruff format/check passed on all S5G implementation and test files. App-environment Pyright
  reported `0 errors, 0 warnings, 0 informations`. Strict OpenSpec is valid; `git diff --check`
  passed. Scope/frozen-source review found no legacy V042, source corpus, original PostgreSQL,
  Milvus, recovery checkpoint, active pointer, product cutover, push, PR, or archive mutation.
- The final merged specification/code-quality and migration/write-safety self-review found zero
  open Critical/Important findings. Task 5.7/S5G is Accepted; Task 6.3 may resume.

## S6C task 6.3 typed domain projection acceptance — 2026-07-13T09:56:27Z

- The Accepted Task 6.2 scenarios are GREEN through one deterministic `DomainInclusionEngine`.
  Professor/Paper/Patent approved scope and Company skeleton/incremental validation remain
  evidence-bound; query-time Web remains outside canonical inclusion. Review REDs proved and then
  closed two sibling defects: an uncited approved record cannot admit evidence from an out-of-scope
  record, and Company validation dimensions cannot cite another canonical subject's assertions.
- One `DomainProjectionBuilder` emits explicit Professor, Company, Paper, and Patent Pydantic roots,
  all 28 catalog subobject types, proportional optional fields, deterministic manifests/counts/
  hashes, exact inclusion lineage, and exact S5 selected assertion/decision lineage. Unknown fields,
  duplicate scalars, dangling/cross-wired candidate evidence, future observations, release/domain/
  cardinality drift, and validity invention/drop/mismatch fail closed.
- The packaged runtime catalog is byte-identical to Accepted Task 6.1 and has no `.agents` runtime
  dependency. The built wheel contains the catalog, all five S6c modules, and C2_0009; the wheel and
  source catalog SHA-256 both equal `e0c72585…55e3`.
- C2_0009 is the single descendant of C2_0008. It creates typed/filterable four-domain roots and
  typed subobject tables, inclusion/manifest/lineage tables, append-only guards, exact foreign keys,
  candidate release/build checks on every insert surface, precision-valid date/instant storage,
  wrong-domain reference guards, deterministic restart reconstruction, and populated-downgrade
  refusal. No active release/index pointer exists in or is changed by this slice.
- The original stale test that treated C2_0007/C2_0008 as a permanent head failed RED with C2_0009;
  it now proves one linear history and the identity adapter's accepted minimum revision while each
  owning migration retains its exact parent test.
- The first post-S5G Pyright run produced eight RED errors: the adapter called `isoformat()` on
  temporal wrappers and fixtures passed native dates into explicit temporal fields. Shared
  `TemporalDateValue`/`TemporalInstantValue` encoding/decoding closed them; a real Professor project
  now restarts with `date` precision and exact `2025-01-01`/`2027-12-31` bounds.
- Migration review added two real PostgreSQL REDs: non-canonical naive instant text was accepted by
  the old shape check, and child rows could be appended by direct SQL after the release became
  active. C2_0009 now reuses C2_0008 canonical temporal validation and gates every manifest,
  inclusion, root, subobject, and lineage insert on the exact candidate release/build.
- Final pure inclusion/projection matrix: `36 passed`. Current complete no-external-database
  Canonical V2 matrix: `192 passed, 125 skipped, 9 xfailed`; all xfails are future public
  build/read/answer/publication and Accepted Task 6.6 path-policy REDs.
- Final real network-none/no-port disposable PostgreSQL projection matrix: `13 passed`. It covers
  schema/catalog materialization, exact restart/replay, multiple roots, rejected/zero-child state,
  conflict/rollback, simultaneous identical/conflicting writers, writer/downgrade locking,
  cross-domain inclusion ownership, direct SQL shape/lineage/hash/time/candidate guards, empty
  downgrade/re-upgrade, and populated downgrade refusal.
- Ruff format/check passed on ten S6c files; app-environment Pyright reported `0 errors, 0 warnings,
  0 informations`; strict OpenSpec and diff checks passed. The explicit backup gate and disposable
  target are rechecked by every adapter/test boundary. No original/recovery/durable-candidate
  database, Milvus, provider, legacy V042, publication/query/answer path, push, PR, archive, or
  product/data/index cutover changed.
- The merged specification/code-quality and migration/write-safety review closed six Important
  findings and has zero open Critical/Important findings. Task 6.3/S6c is Accepted.

## S6D task 6.4 relationship RED acceptance — 2026-07-13T10:12:13Z

- Branch comparison proved `codex/canonical-v2-s6d-red` diverged before Tasks 6.2/6.3 and contained
  exactly two unique files: the S6D slice contract and one relationship RED module. The original
  branch independently reproduced exactly `9 xfailed`; forced RED produced exactly nine
  `_MissingTargetModule` failures for the absent exact product module.
- The integration used the reviewed patch without committing the old branch topology. No product,
  shared-contract, migration, catalog, database, Milvus, provider, release, path, query, answer, or
  consumer behavior was copied from the side branch.
- Nine strict groups cover identity/lifecycle, organization/role, scholarly output, intellectual
  property, Company business/product/event, taxonomy/topic/geography, evidence/lineage, all eight
  cross-domain directions, and canonical/derived/session layer non-fabrication. They bind catalog
  type/version, endpoint orientation/kind, roles, proportional time/state, required evidence kinds,
  retained artifacts/assertions, source-to-canonical assignments, and explicit selected decisions.
- Integration review found one additional Important gap: the parallel RED branch accepted
  string-only canonical/typed-subobject endpoints without proving those objects existed in the now
  Accepted Task 6.3 output. The request now carries content-validated S6c typed domain roots and
  nested Company subobjects. Dedicated RED cases reject a dangling canonical identity and a
  dangling typed subobject; assignments remain insufficient without the projection registry.
- Current-line normal RED remains exactly `9 xfailed`; forced `--runxfail --no-cov` remains exactly
  nine missing-target failures. Ruff format/check passed and app-environment Pyright reported
  `0 errors, 0 warnings, 0 informations`.
- The merged specification/code-quality review has zero open Critical/Important findings. Task 6.4
  is Accepted as a test-only slice; Task 6.5 owns all production relationship implementation and
  persistence.

## S6A2 catalog authority source rebind — 2026-07-13T10:49:49Z

- Reported case reproduced: the Task 6.1 catalog/shared baseline failed seven of its eight catalog
  tests at the first full-file authority check. Accepted S5G commit `5771abf` had added temporal-
  precision behavior to both `design.md` and `canonical-v2-knowledge/spec.md` after Task 6.1 froze
  their SHA-256 values; the catalog builder constant and seed manifest were not rebound.
- Sibling search compared all 14 authority paths. Exactly those two S5G files drifted; the other 12
  matched. The review and packaged catalog copies were mutually byte-identical but jointly stale,
  and runtime/test constants named the same stale content/file identity.
- The deterministic builder source identity, catalog seed, content self-hash, packaged copy, runtime
  constants, and relationship RED identity were rebound as one set. Catalog semantics are unchanged:
  14 sources, 9 shared fields, 101 domain fields, 28 subobjects, 7 families, 34 relationship types,
  42 scenarios, 8 traversal directions, and 5 deferred owners. A normalized diff excluding only
  source SHA and content self-hash fields was empty.
- Current catalog content SHA-256 is `8ad9e719579b834f51128788f49d091913c0c90e3b047aac9b2f83cc794441d7`;
  file SHA-256 is `b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0`.
- Deterministic builder write/check passed; eight catalog plus sixteen Accepted shared-contract tests
  passed (`24 passed`); review/runtime bytes matched; runtime import returned the exact new hashes;
  Ruff, Pyright, and the post-fix all-14-source scan were clean.
- Defect class: L6 Evidence/Provenance Violation + C1 Test-Matrix Gap. The invariant is now required
  in every later S6 acceptance and the aggregate mainline promotion gate. No catalog semantics,
  database, migration, Milvus, provider, release, source, or product data changed.

## S6E Task 6.5 pure relationship projection — 2026-07-13T12:35:08Z

- Implemented one package-internal deep module seam,
  `RelationshipProjection.project(RelationshipProjectionRequest)`, over the installed packaged
  34-type catalog. Product code never reads `.agents`; it verifies the supplied catalog identity
  against the content-addressed runtime resource.
- The module validates exact Task 6.3 content-bound canonical roots and typed subobjects, including
  parent and concrete subobject type; catalog endpoint orientation, role vocabulary/ownership,
  state, proportional time, required evidence kinds, and retained reference closure; and exact
  source-assignment/assertion/decision/policy/evidence continuity. Rejected constraints produce no
  decision/current projection; accepted rejected-state decisions retain evidence but are not current.
- Four-domain root relationships retain the shared S5 `RelationshipAssertion` and
  `RelationshipDecision` models. Registry/subobject/lineage endpoints retain typed assertions and
  typed decisions without fabricating canonical identity IDs. Derived/session probes cannot project
  canonical facts, source-potential scenarios remain non-evidence, and direction probes validate the
  exact catalog scenario, endpoint registry, and type list without invoking path eligibility.
- S5G temporal precision remains exact. Candidate/assertion intervals reject mixed precision or
  reversed values. A date-only validity boundary compared with request `as_of` returns currentness
  `indeterminate` and `explicit_calendar_context_required` unless the caller supplies the named
  Gregorian/timezone `TemporalComparisonContext`; no date is coerced to an instant.
- Review found and closed four Important gaps beyond the original RED: typed subobject ID/parent
  checks did not bind concrete type; shared assertion attributes/time were not field-for-field
  continuous; date-only currentness was silently omitted without an indeterminate result; and
  direction probes did not prove their endpoints existed in the S6c registry. A fifth decision-
  shape guard now rejects accepted typed decisions that select no assertion. Zero Critical/Important
  findings remain.
- GREEN evidence: focused relationship contract `9 passed`; deterministic Task 6.1 catalog/shared
  baseline `24 passed`; full no-external Canonical V2 `201 passed, 125 skipped, 9 expected xfailed`;
  Ruff format/check passed; app-environment Pyright reported zero errors; builder `--check` passed.
- This pure sub-slice is Accepted independently. OpenSpec Task 6.5 remains unchecked and the task
  count remains 33/75 because durable relationship assertion/decision/current persistence is still
  required. No migration, database, Milvus, provider, release, query, answer, admin, source, product
  data, push, PR, archive, or cutover changed.

## S6E2 Task 6.5 relationship persistence acceptance — 2026-07-13T13:54:12Z

- C2_0010 is the sole linear descendant of C2_0009. It adds immutable relationship projection run,
  shared-ledger membership, typed assertion/decision/decision-edge, candidate-outcome, and unified
  current surfaces. It refuses populated downgrade, gates every new release-scoped row plus existing
  shared relationship decision/edge inserts to candidate releases, and validates canonical or typed
  subobject endpoints against durable release-scoped owners.
- `RelationshipProjectionStore.persist(request, result)` reprojects exact typed input, content-binds
  request and result, rechecks the accepted backup gate and explicit disposable target, verifies
  retained artifact/source-record lineage, reuses exact existing shared assertions/decisions, and
  atomically persists typed and current surfaces. Exact replay is a no-op under an advisory lock;
  restart rejects run-envelope, normalized-row, role-edge, shared-content, and retained-evidence
  cross-wires.
- The merged implementation/migration review closed five Important findings: explicit upstream
  shared decision/relationship IDs replaced locally synthesized IDs; exact replay now binds request
  content as well as result content; restart binds payload to the durable run envelope; and shared
  assertion plus retained artifact lineage is reconstructed and checked rather than trusting a
  stored hash alone; and factory preflight requires all eight C2_0010 tables. Durable
  decision/canonical-relationship IDs are unique before persistence. Zero Critical/Important
  findings remain.
- Real PostgreSQL evidence used only marked, owned disposable sibling databases under
  `canonical_v2_s6c_base`. The focused relationship matrix passed `13 passed`; it covers fresh and
  empty downgrade/re-upgrade, typed and pre-existing shared-ledger round trips, exact replay/restart,
  concurrent convergence, changed-request conflict, transaction rollback, append-only and
  candidate-release guards, target/marker/backup failure, endpoint rejection, retained artifact
  mismatch, shared same-hash/wrong-content rejection, run-envelope corruption rejection, and
  incomplete-schema factory refusal. The
  separate current-head inventory check passed `1 passed` on
  `canonical_v2_s6c_base_s6e2_compat`.
- Final checkpoints: relationship pure plus no-database store surface `10 passed, 12 skipped`;
  complete no-external Canonical V2 `202 passed, 137 skipped, 9 expected xfailed`; deterministic
  catalog builder `--check` plus catalog/shared contracts `24 passed`; Ruff check/format passed;
  app-environment Pyright reported `0 errors, 0 warnings, 0 informations`; strict OpenSpec passed.
- Task 6.5 and its three relationship acceptance criteria are Accepted at 34/75 tasks. The original
  pgtest, original Milvus, S6c base business tables, recovery checkpoint, source/product data,
  release/index pointers, push, PR, archive, and cutover were not modified. Task 6.7 is next.

## S6G Task 6.7 path eligibility acceptance — 2026-07-13T14:18:02Z

- Implemented one deterministic, storage/provider-independent deep module,
  `PathEligibilityEngine.evaluate(PathEligibilityRequest)`, over the exact six-path published
  registry. It consumes separate inclusion, typed current projection, accepted/rejected relationship,
  named hard-invariant, and optional merge-redirect decisions; it exposes no global `ready` field or
  compatibility branch.
- Every path returns one shared `PolicyDecision` whose content-addressed identity binds the complete
  policy, subject, release, path, outcome, limitations, hard exclusions, evidence, and evaluation
  time. The result is also content-bound. Ordinary incomplete enrichment and Paper `unverified`
  status remain evidence-backed limitations/gaps; inclusion `review` remains review and cannot
  promote an identity without a current projection.
- Verified relationship traversal consumes the installed content-addressed Task 6.1 catalog,
  preserves its canonical source/target orientation for all eight forward/inverse request
  directions, and binds source inclusion, relationship assertion, and complete target typed-field
  lineage. Rejected attribution excludes only traversal and does not reject independent Paper exact
  lookup. Broken references remain path-scoped; object-level named invariants cover all paths; a
  merged predecessor resolves only to one current survivor.
- The merged specification/code-quality review closed six Important findings: duplicate quality
  codes across projections could overwrite evidence; decision identity omitted policy ID/content;
  release/subject/path/evidence continuity lacked negative coverage; traversal omitted part of the
  target endpoint lineage; related relationship inputs could be silently ignored without a requested
  direction; and inclusion review could be promoted as admitted. Zero Critical/Important findings
  remain.
- RED evidence remained exact before implementation: normal execution was `5 xfailed`; forced RED
  was five direct missing-target failures. GREEN focused path-policy evidence is `9 passed`; complete
  no-external Canonical V2 is `211 passed, 137 skipped, 4 expected xfailed`; deterministic catalog
  builder `--check` plus catalog/shared contracts is `24 passed`; Ruff and app-environment Pyright
  pass. Strict OpenSpec and staged diff/secret/scope checks passed at the commit checkpoint.
- Task 6.7 and its three path acceptance criteria are Accepted at 35/75 tasks. No migration,
  database, Milvus, provider, release/index pointer, retrieval/public interface, source/product data,
  push, PR, archive, or cutover changed. Task 6.8/Aggregate S6 is next.

## S6H Task 6.8 / Aggregate S6 acceptance — 2026-07-13T14:48:01Z

- The aggregate review accounts for exactly four typed domain roots, 9 shared and 101 domain fields,
  28 typed subobjects, 34 relationship types across seven families, 42 source-accounting scenarios,
  all eight cross-domain directions, and six independently evaluated published paths. The detailed
  requirement, sibling, and side-branch matrix is in `s6-aggregate-review.md`.
- Focused inclusion/domain/relationship/path verification was `54 passed`; complete no-external
  Canonical V2 was `211 passed, 137 skipped, 4 expected xfailed`. The xfails are exactly
  KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, and ReleasePublication, owned by S7-S9.
- Focused C2_0009/C2_0010 real persistence was `26 passed`. The first full real-PostgreSQL run was
  `336 passed, 3 failed, 9 errors, 4 xfailed`: nine errors were the known S4C exact-database-name
  harness contract; three failures revealed older relationship-integrity tests creating accepted
  releases before their decisions. Sibling search found a fourth self-supersession false positive
  hidden by the same candidate-release guard.
- All four relationship tests now follow the real candidate→accepted→next-candidate lifecycle. The
  focused repair was `4 passed`; corrected general real Canonical V2 was `338 passed, 4 xfailed` and
  the separately owned fixed-name S4C matrix was `10 passed`, for 348 real passes. C2_0010 and all
  production/migration behavior remain unchanged.
- Side-branch accounting is complete: S6c's stale C2_0008 patch is superseded by S5G C2_0008 plus
  the accepted C2_0009 superset; all 9 S6d and 5 S6f RED groups are present and strengthened; the
  Task 6.1 preparation-only artifacts explicitly defer now-accepted policy and remain abandoned and
  untouched in their owner worktree.
- Every owned S6H and fixed-name S4C database was dropped. The explicit S6c base has zero schemas and
  user tables; `pgtest` remains paused; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Deterministic catalog `--check` passed; catalog/shared contracts were `24 passed`; Ruff format and
  check passed; app-environment Pyright reported zero findings; strict OpenSpec is valid at exactly
  36/75; the formal S2B gate remains `accepted/50`. Frozen FPI salvage and original Milvus hashes
  remain `cef8eb6b...fdfbb7` and `43ef203e...867cc`; the recovery lab remains network-none/no-port.
- The merged specification/code-quality, persistence/write-safety, sibling-pattern, and side-branch
  review has zero open Critical/Important findings. Task 6.8 and Aggregate S6 are Accepted at 36/75.
  S7-S12, release/index/product cutover, push, PR, and OpenSpec archive remain unstarted/forbidden.

## S12A Task 12.1 isolated Candidate — 2026-07-22

- Status is Candidate, not Accepted. Task `12.1`, all OpenSpec task/acceptance checkboxes, `main`,
  active release state, production resources, Push/PR, archive, and Cutover remain unchanged.
- The user authorized behavior-preserving identity-resolution and DomainProjection performance
  prerequisites. Their exact owner command was
  `uv run pytest -q tests/canonical_v2/test_canonical_identity_resolution_contract.py tests/canonical_v2/test_domain_projection_contract.py -n0`
  and reported `87 passed in 8.24s`.
- The current focused S12A command was
  `uv run pytest -q tests/canonical_v2/test_knowledge_build_isolated.py ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py -n0`
  and reported `67 passed in 307.09s`. Ruff check and Pyright over the same changed implementation
  surface reported zero findings.
- The successful owned r10 build used release `candidate-s12a-20260722-r10`, run
  `s12a-build-20260722-r10`, isolated PostgreSQL database
  `miroflow_candidate_s12a_20260722_r10`, and staging/index roots below
  `/var/tmp/mirothinker-canonical-v2-s12a/r10`. The evidence file is
  `s12a/complete-candidate-build-envelope-r10.json`, raw SHA-256
  `2f797e0df058a9a3969a7d01b97df2492a156a64ff1436aa33588100bc6831e7`.
- Current-model envelope validation passed. Canonical envelope, receipt, and handoff hashes are
  `69e359c903488f8d2ce237e042d3ffd5f410463081e31620c0fc7cb3911980a8`,
  `e412af8405ba4607a62b7dc54bc8898e2ea63f71d49f218562a93b87e6b96d76`, and
  `f05514cfefb129840e20fa4ead92fbb7cd40981293c30cc9e7c2de229aa984a8`.
- Independent PostgreSQL readback found 5,561 landing records, 1,037 canonical identities, 4,148
  canonical decisions and domain-lineage rows, 1,037 Company projections, zero other public-domain
  projections, zero current relationships, one relationship run, 5,561 gaps, one release/build
  manifest, and 1,044 manifest sections. Every landing record has exactly one gap evidence
  reference and no gap references a missing landing record. Gap domains are Company 1,037,
  cross-domain 580, Paper 574, Patent 1,931, and Professor 1,439.
- Independent `audit_isolated_index_snapshot` with recorded embedding authority
  `a5b57005eb48a0692ae946d83c02ce54df0280a8274527f94c29d79d81266200` and dimension 32 found
  1,037 unique points and 1,037 unique lookup documents, with 8 vector and 7 lookup manifests.
  Physical snapshot SHA-256 is
  `438e7c3f702e7bb16d145ac584562d8ef1872033bfd6e685ce7079e04c5be5fe`; release verification has
  zero missing, extra, stale, or cross-release points.
- `publish.active_release` is absent before and after. Original `pgtest` remains paused. Original
  Milvus was never opened or rehashed. r1-r9 resources and historical evidence are retained; no
  cleanup was performed.
- Production `--serve` intentionally fails closed before builder construction. Task `12.2` owns the
  content-addressed serving bundle and live query/answer/Web gates; the injected serving test proves
  only the handoff interface.
- Final named-only independent review returned GO for the isolated S12A Candidate with zero open
  Critical or Important findings. The reviewer explicitly confirmed that this is not external
  Accepted and that Task `12.1` must remain unchecked until the system/acceptance decision.
- The formal ledger remains `70/80` tasks and `49/97` acceptance checks. The next action is the
  user's system/independent acceptance of Task `12.1`; only after acceptance may the task checkbox
  and local task commit be created.

## S12A Task 12.1 accepted isolated r12 candidate — 2026-07-23

- The user authorized completion of the open implementation work with reduced ceremony. S12A was
  hardened against path-replacement SQLite reads, duplicate/deep JSON, incomplete payload-path
  accounting, inherited/remote PostgreSQL configuration, and semantic live-schema drift. Final
  implementation/test/runner/runner-test SHA-256 values are
  `85b4ca8b89bb1e9c8870957933002e270e59916b8367f443d3ee267932298efa`,
  `d8c8174f31d226468c8b7fe85fd543c022ea74f7cb88a461d1b33dd98753dff4`,
  `0279b2428c11bd07fa7debbed81705712fc25b5938ec1f0c2aa35eaab82fa682`, and
  `a85ea8da306b665550f668a6aaeec83db5cff1f4701919f4492044ac62b59403`.
- The fresh formal run used release `candidate-s12a-20260723-r12`, run
  `s12a-build-20260723-r12`, database `miroflow_candidate_s12a_20260723_r12` at numeric loopback
  `127.0.0.1:55450`, and staging/index roots under
  `/var/tmp/mirothinker-canonical-v2-s12a/r12`. The database matched exact C2_0011 semantic catalog
  SHA-256 `7605fd00290741478b0cda727b9a6869e731d3a94d0b7bd6ab5ad9b8a59fcdfc` before effects.
- Current evidence is `s12a/complete-candidate-build-envelope-r12.json`. Raw/canonical envelope,
  receipt, and handoff SHA-256 values are
  `a2684f9b9bd42c8727625fa7e057f654c6539a6e97924eccfdfb913fdfef9cbc`,
  `77cde16c037aec888e07a677b3f96effd27a75f3eeb68a4f38c5fdb2a6a88383`,
  `5ae974b6af80980864bac751812b12fb7c468a4449331db4a85b47c4453437a8`, and
  `f18af1854a92ef2d76816a8f3f3a9a724fb5ab233de6020f9c161c5100cf00bc`. The historical unsuffixed
  r6 file was restored byte-for-byte at raw SHA-256
  `ab21c0a60a5d85a2abd51724b945a79e5f99c121601eeb995870cb974b79acb9`; r10/r11 are retained stale
  evidence.
- Independent read-only PostgreSQL audit found 84 owner tables, 5,561 parsed landing records, zero
  source errors, 1,037 canonical identities/identity decisions/domain-inclusion decisions, 4,148
  domain-lineage rows, 1,037 Company projections, zero Paper/Patent/Professor/current-relationship
  projections, one relationship run, 5,561 gaps, one release/manifest, 1,044 manifest sections, and
  no active release. Every gap has exactly one distinct landing-record evidence ID; every landing
  record has exactly one gap; no foreign-release row exists. Durable registry SHA-256 is
  `5092f40fb0759dd69a297fa505b8cb50ab09fbac39d7209e602c69cffea3732f`.
- Physical index audit opened only a byte-exact temporary copy because Milvus Lite creates a
  transient lock beside an opened database. It found 1,037 unique points, 1,037 unique lookup
  documents, 8 vector manifests, 7 lookup manifests, and only the r12 release. Index receipt and
  physical snapshot SHA-256 values are
  `d38e1c2fe69739d4779deb6637b455d0cf6fff8d2c42f7ccd5ac63bb179f4095` and
  `20cc5fd309056f714e09038465d3cec805e239752f1b709e0e92ba269f46cabe`. The formal index marker,
  lookup, and Milvus files remained byte-identical before/after at `dedcb86b...65e4`,
  `3bd292db...d8b`, and `1b234c99...c0f8`, with no lock file.
- Verification commands and results:
  - `uv run pytest -q tests/canonical_v2/test_knowledge_build_isolated.py ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py -n0` — `104 passed in 340.20s`.
  - `uv run pytest -q tests/canonical_v2/test_canonical_identity_resolution_contract.py tests/canonical_v2/test_domain_projection_contract.py -n0` — `87 passed in 10.58s`.
  - OpenSpec Task 12.1 owner matrix — `169 passed, 2 skipped in 802.42s`; skips require all four
    explicit external `CANONICAL_V2_TEST_*` settings.
  - Complete no-external Canonical V2 — `542 passed, 148 skipped, 3 warnings in 837.40s`; warnings
    are expected serialization diagnostics from intentional invalid-value tests.
  - Complete Canonical V2 Ruff and focused format checks pass; Pyright reports
    `0 errors, 0 warnings, 0 informations`.
  - `uv lock --check --offline` and `uv build --wheel --offline` pass. The first attempted combined
    `uv build --wheel --offline --locked` was rejected by this uv version before any build. The
    equivalent two-step gate produced a 282-entry wheel with SHA-256
    `f3566145f55e2b2fc49172d79818d93e1efd2d0c98cb4e817e621fe8636abe68`; embedded
    `knowledge_build_isolated.py` exactly matches source and the wheel contains no tests/`.agents`.
- Final source, safety, and evidence reviews are GO with zero Critical/Important findings. Original
  `pgtest` remains paused; original Milvus was not opened or rehashed; active release is absent;
  no production resource, pointer, Push, PR, archive, or Cutover changed.
- S12A and exactly Task `12.1` are Accepted. The ledger is now `71/80` tasks and `49/97` acceptance
  checks. No commit was created because explicit commit authorization was not supplied.
- Remaining tasks are hard-blocked, not silently waived: Task `2.8` requires attributable two-human
  decisions/calibration; Tasks `8.1`, `8.8`, and `9.8` require the missing reviewed populations and
  real-provider evidence; Task `12.2` lacks its serving bundle and those upstream gates; Tasks
  `12.3`-`12.4` await the final aggregate; Task `12.5` needs explicit final user acceptance; Task
  `12.6` needs separate Cutover authorization.

## S2C3C2 single-human review workbench Candidate — 2026-07-24

- Status is Candidate, not Accepted. By explicit owner decision, one attributable human now owns
  the exact 29 contract decisions, 23 exclusion decisions, and 60 blind calibration labels under
  `single-human-global-stratified-v2`. Task `2.8`, Tasks `8.1`/`8.8`/`9.8`, all real-human
  acceptance items, and Tasks `12.2`-`12.6` remain unchecked.
- Frozen raw SHA-256 identities remain packet
  `222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e`, workload
  `0e0e5bbc1a101d4a21fc99c523b59ad81a344420d13fc57d5f11000570e8f494`, and policy
  `9900ea9a6cb20c928fb07f9c38f43b4bc0d6f42efad0978aab6a341cfa3b92c5`. The workload is exactly
  `29 + 23 + 60 = 112`, with calibration quotas `20/10/10/10/10`.
- The isolated Admin surface now includes the deep SQLite `ReviewWorkspace`, review-only factory
  and API, semantic static workbench, append-only decisions and exports, prior-runtime crash
  recovery, verified-only/no-symlink export reads, exact judge authorization, and an explicit
  launcher defaulting to `0.0.0.0:18189`. Raw idempotency keys and pre-seal judge signals are never
  exported. The original Candidate factory remains isolated.
- `validate_review_export_v2.py` imports no Admin module and independently recomputes canonical/self
  hashes, frozen identities, event/current projections, authorization/run/recovery/response chains,
  and all Global-60 gates. `apply_review_export_v2.py` internally invokes that validator before any
  write and atomically creates seven new v2 files without changing v1. Evaluator-v2 independently
  recomputes the 60-pair metrics and binds authorization workload, human snapshot, completed run,
  export, policy, and reviewed-v2 identities; the v1 evaluator branch remains compatible.
- Verification commands and results:
  - `cd apps/admin-console && uv run pytest -q tests/test_canonical_v2_review_workspace.py tests/test_canonical_v2_review_http.py tests/test_canonical_v2_review_ui.py tests/test_canonical_v2_review_launcher.py` — `117 passed in 25.87s`.
  - `cd apps/miroflow-agent && uv run pytest -q ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c -n0` — `105 passed in 15.91s`.
  - `cd apps/admin-console && uv run pytest -q tests/test_canonical_v2_consumer_migration.py tests/test_canonical_v2_operations_api.py tests/test_canonical_v2_real_preview_ui.py` — `12 passed in 19.47s`.
  - Ruff over the changed Admin and S2C Python surfaces passed. Root Pyright over all changed
    production/tool modules reported `0 errors, 0 warnings, 0 informations`.
  - `openspec validate rebuild-canonical-v2-knowledge-platform --strict` and `git diff --check`
    passed. JavaScript syntax and the mutation-coordinator behavior checks run inside the UI suite.
- Real browser verification used a fresh `/tmp` implementation-only ledger. It covered registration,
  contract/exclusion/calibration task rendering, final decision persistence across reload, absence
  of pre-seal judge/gold fields, audit export, and a real two-session stale sequence:
  `POST decision 200 -> stale POST 409 -> draft restore PUT 200 -> explicit confirmation -> POST
  200`. At 375 px, `scrollWidth <= innerWidth`; desktop and mobile screenshots had no overlap, and
  the browser console was empty.
- The observed audit package was `export:84e3a5cdbb1889d46ccdeedfaa3692ce`, raw SHA-256
  `2866b65179944b46c36d74a2d402619da61267cfe4f15173caa38da3e6bf203e`, content SHA-256
  `60d00dbfdd9b366150735884f03e827015f43647a8127dd330f53f7ec2333ffd`, mode
  `review_evidence`, evidence class `implementation_test`, `acceptance_eligible=false`,
  `task_2_8_eligible=false`, and judge visibility `hidden_until_sealed`. It is test evidence only
  and cannot be applied or reinterpreted as acceptance.
- Focused recovery/export and validator/application/evaluator reviews ended GO with Critical `0`
  and Important `0`. The reviews closed same-runtime recovery, prepared-export read, symlink
  replacement, raw idempotency, forged-validator-receipt, aggregate-summary, authorization/workload,
  human-snapshot, and completed-run cross-wire failure modes.
- Original PostgreSQL and Milvus were not started or opened, active-release state was not read or
  changed, and no production resource, source artifact, v1 review artifact, S12A artifact, commit,
  Push, PR, archive, cleanup, promotion, or Cutover changed. The formal ledger remains `71/80` tasks
  and `49/98` acceptance checks.

## S2C3C2 human-readable review presentation repair — 2026-07-25

- Replaced raw JSON as the primary review surface with a deterministic `review_presentation.js`
  translator. Contract review now states the review purpose, the all-or-nothing approval condition,
  readable claims/entities/variants/enumeration/stage expectations, and decision guidance. The raw
  contract remains available only through the expandable audit structure. Exclusion and calibration
  tasks now also render their review purpose, frozen material, and decision criteria in human terms.
- The renderer is versioned as `canonical-v2-human-review-renderer-v2`; the presentation asset is
  content-hashed together with the existing static assets. Unknown structures still fail closed by
  disabling contract approval and directing the reviewer to the audit structure.
- Regression coverage runs the exact 29 frozen contract rows through the translator. It rejects any
  raw-object fallback or untranslatable known contract and specifically covers the `wb-r009` safety
  prohibitions/qualified outcomes and `wb-r012` near-name Company scenario. Focused presentation
  tests, the full review suite, and UI asset-binding tests pass.
- Browser verification used a fresh implementation-only ledger and checked readable contract,
  exclusion, and blind-calibration screens. `wb-r012` presents the target Company, near-name
  prohibition, protected-name, Web, evidence, and rendered-answer requirements as a checklist. At
  390 px the page has no overlapping text; browser console and page-error output are empty.
- An earlier formal state contained one registration/session but zero decisions, drafts, judge runs,
  seals, or exports. Its v1 renderer identity correctly failed admission after the v2 renderer change;
  it remains intact. A new empty `formal-state-v3` ledger now serves the same isolated `0.0.0.0:18189`
  endpoint for the real human round. No human decision, review export, Task 2.8 acceptance, or
  Canonical PostgreSQL/Milvus state changed.
- Current checks: `121 passed in 26.04s` for the complete Admin review suite; Ruff check/format,
  JavaScript syntax, strict OpenSpec validation, and `git diff --check` pass. Targeted Pyright for
  the changed service and UI test reports `0 errors, 0 warnings`; the pre-existing full workspace
  review-test typing diagnostics remain outside this repair.

## Lean customer-benchmark E2E rebaseline — 2026-07-26

- The user canceled the current human-review workflow and Task `2.8` after direct use showed that
  contract review, exclusion review, and blind calibration did not answer the product question:
  whether the real system gives useful, correct, source-grounded answers.
- `docs/测试集答案.xlsx` is confirmed as the customer-provided case-specific Ground Truth. Its one
  sheet contains 17 conversation groups and 25 query turns. Query, answer, and key points are read
  together; explicit key-point corrections override inaccurate historical answer fragments. The
  workbook is never runtime knowledge or an exact-wording template.
- Tasks `2.8`, `8.1`, `8.8`, and `9.8` are retired as separate gates. Their implementation and
  evidence remain intact as non-normative history; no review decision, label, judge run, export, or
  cleanup was fabricated.
- The remaining implementation is Tasks `12.2`-`12.6`: build a serviceable four-domain isolated
  Candidate and serving bundle, run representative real-chat smoke cases plus all 25 workbook turns,
  run the minimal safety/changed-surface checks, obtain direct user acceptance, and retain separate
  cutover authorization.
- Development verification is intentionally lean: changed-module tests, one Candidate population/
  relationship/parity/source-isolation smoke, approximately eight representative chat cases, one
  final 25-turn replay, focused Ruff/Pyright, strict OpenSpec validation, and `git diff --check`.
  Independent slice reviews, scaled human labels, repeated broad suites, and duplicate evidence
  envelopes are not required without a concrete regression or safety reason.
- Current physical state is unchanged by this documentation rebaseline: r12 remains Company-only,
  original PostgreSQL remains paused, original Milvus remains unopened, and no active release,
  production resource, commit, Push, PR, archive, cleanup, promotion, or Cutover changed.

## S12C Tasks 12.3/12.4 customer replay Candidate — 2026-07-26

- Status is Candidate, not user Accepted. Release `candidate-s12c-20260726-r8` / run
  `s12c-build-20260726-r8` contains 1,037 Company, 262 Paper, 1,931 Patent, and 554 Professor
  projections plus 339 evidence-backed relationships. The isolated index contains 4,338 points and
  3,784 lookup documents with zero missing, extra, stale, or cross-release identities.
- The serving bundle content hash is
  `5c48468be9a04529f733a4a3e6b87b1e1a2b4d00d24dd4ebeae7ecd1d0ca15fc`. Envelope raw/canonical,
  receipt, and handoff hashes are `93ca2f0c...fc0086`, `2ca631dc...f09c28`,
  `10e3e685...2af40c`, and `12b23128...107a2`.
- Final report artifacts are `s12c/customer-workbook-replay-r6.json` and `.md`. They bind workbook
  SHA-256 `edd95009...80c5b`, execute 17 distinct cookie sessions and 25 ordered turns, and report
  `25 ok / 0 failure`. Replay content SHA-256 is `003486c2...5a72b9e`; raw JSON/Markdown hashes are
  `0ff2441b...c4fc8c` and `0a20e7ae...57466`.
- Systemic repairs cover real Qwen embeddings, answer-eligible evidence closure, exact/lexical
  identifier ownership, exact-entity selection without vector-neighbor padding, accepted
  email/homepage identity merge, bounded Company name transposition, focused missing-entity Web
  fallback, per-session execution locks, and typed independent-turn topic switching.
- Real-chat verification confirms one Ding Wenbo answer and founder traversal, Wujie Zhihang without
  the near-name UAV Company, one pFedGPA Paper across its follow-up, focused Hualichuang and Aibo
  Hechuang Company answers, and exact `CN117873146A` resolution. A separate three-turn smoke proves
  the exact Patent changes `active_anchor`; the next relationship traversal starts from that Patent.
- Product gaps remain visible rather than fabricated: Company headquarters filtering (rows 6/15),
  the Waseda entrepreneur (row 20), Wang Xueqian assessment (row 25), embodied-data route comparison
  (row 35), the pFedGPA URL, and several incomplete broad analyses. Web timed out on rows 14 and 27;
  both retained evidence-bound local answers and explicit timeout traces.
- Focused verification:
  - `cd apps/miroflow-agent && uv run pytest -q tests/canonical_v2/test_knowledge_serving_isolated.py tests/canonical_v2/test_internal_reference_projection_contract.py::test_release_scoped_exact_lookup_binds_physical_bundle_and_public_trace -n0` — `27 passed in 17.27s`.
  - `cd apps/admin-console && uv run pytest -q tests/test_canonical_v2_chat_http_adapter.py` —
    `11 passed in 12.53s`.
  - `cd apps/admin-console && uv run pytest -q ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/test_customer_workbook_replay.py` — `2 passed in 0.78s`.
  - Focused Ruff passed. Targeted Pyright in the Agent project and root project environment each
    reported `0 errors, 0 warnings, 0 informations`.
  - `openspec validate rebuild-canonical-v2-knowledge-platform --strict` and `git diff --check`
    passed. Active Canonical V2 production modules contain no workbook path, row, reference answer,
    case ID, exact workbook query, or Ground Truth shortcut.
- Both `http://127.0.0.1:18188/chat` and `http://100.64.0.4:18188/chat` return HTTP 200. The service
  remains bound to `0.0.0.0:18188` for direct user evaluation.
- Original `pgtest` remains paused. Original Milvus remains byte-identical at SHA-256
  `43ef203e...867cc`; the Candidate database is disposable; `publish.active_release` contains zero
  rows. `main` remains `f0e6224e...d8f6`, HEAD remains `977d4f23...7415`, and no commit, Push, PR,
  promotion, archive, cleanup, or Cutover occurred.
- Tasks 12.3 and 12.4 are complete. The ledgers are now `78/80` tasks and `26/35` acceptance checks.
  Task 12.5 remains open for explicit direct-user acceptance; Task 12.6 remains open for separately
  authorized Cutover.

## S12C Candidate runtime Web-gap repair — 2026-07-27

- The same read-only `candidate-s12c-20260726-r8` now sends the lane-specific contextual query to
  Serper, carries displayed entity names into multi-turn Web lookup, and keeps current-Web evidence
  ahead of unrelated vector neighbors when the question explicitly asks for current, evaluative,
  geographic, or URL evidence.
- The repair also bounds the provider's internal request and curl fallback inside the outer Web-lane
  timeout, binds ephemeral Web handles to the HTTP session, and validates release-authoritative
  Professor handles only for evidence retained after late reranking. These changes remove the
  observed Web timeout and false HTTP 409 integrity-conflict classes without changing the Candidate.
- Focused verification passed: serving `29 passed`, late-selection release-authority regression
  `1 passed`, query planning `5 passed`, and Admin chat HTTP `11 passed`. Changed-file Ruff and
  formatting checks passed; targeted Agent and Admin Pyright each reported `0 errors, 0 warnings`.
- Real HTTP smoke on `0.0.0.0:18188` returned 200 for all three targeted gaps. The Wang Xueqian
  assessment completed in 73.58 seconds with a successful eight-candidate Web lane and five retained
  current-Web items. The pFedGPA two-turn flow returned the local paper profile, then completed the
  URL follow-up in 10.11 seconds with a successful six-candidate Web lane and five retained current-
  Web items. The Shenzhen embodied-intelligence supplier query completed in 7.12 seconds with a
  successful eight-candidate Web lane and two retained current-Web items.
- The smoke also preserves two visible product-quality gaps rather than fabricating completion: the
  Wang response can still mix a same-name Tsinghua researcher and does not yet express the requested
  conditional assessment; the Shenzhen response supplies current industry and supplier sources but
  does not yet produce a complete company-by-company data-route comparison. These are direct-user
  acceptance inputs, not transport or isolation failures.
- Original `pgtest` remains paused, original Milvus remains byte-identical at SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`, and the disposable Candidate
  still has zero `publish.active_release` rows. HEAD, `main`, and the release/index authority are
  unchanged. No canonical write, promotion, archive, cleanup, commit, Push, PR, or Cutover occurred.
- The task ledger intentionally remains `78/80`: Task 12.5 requires explicit acceptance after direct
  user use, and Task 12.6 requires separate explicit authorization before any production-like
  Cutover, archive, or destructive cleanup. Neither gate can be completed by automated verification.

## S12D universal Web, LLM synthesis, and public evidence — 2026-07-27

- The serving path now invokes bounded Web for every normal information request and passes retained
  evidence-bound claims to the configured LLM renderer. Provider or output failure remains a typed
  deterministic fallback rather than the normal answer path.
- The shared `gemma4` and `ark` local route configuration now uses the currently deployed
  `qwen3.6-35b-a3b-fp8` model. A live model-list request exposed the retired model mismatch; a
  minimal generation request and real chat answers then returned successfully with the new model.
- Professor-Company founder evidence is handled generically through the
  `professor_company_role` predicate. The final two-turn HTTP replay returned
  `丁文伯参与创立了深圳无界智航科技有限公司` and `answer_style=llm_synthesized`; no production code
  contains Ding Wenbo, Wujie Zhihang, workbook-row, or exact-query branching.
- Public responses contain `evidence=[]` and `structured_payload={}`. The first-turn citation is the
  official Tsinghua homepage; `/browse`, private-network URLs, internal locators, release IDs, and
  retrieval/selector traces are absent. The public chat page also has no `/browse` navigation.
- Browser verification at 1440x900 and 390x844 found no overlap. `查看依据` starts with `open=false`;
  after expansion its only link is `http://www.sigs.tsinghua.edu.cn/dwb/main.htm`.
- Verification: serving tests `31 passed`; LLM-profile tests `19 passed`; focused latest public/UI
  tests `14 passed`; the earlier complete Admin/UI run before the final private-host/navigation
  assertions reported `23 passed`. Focused Ruff and root Pyright report clean, strict OpenSpec and
  `git diff --check` pass. One later complete Admin/UI rerun was interrupted because it stalled while
  the 8 GB Candidate process was resident; the newly changed tests were rerun directly and passed.
- Release `candidate-s12c-20260726-r8` remains read-only on `0.0.0.0:18188`. No source, canonical,
  index, active pointer, production resource, commit, Push, PR, promotion, archive, or cleanup changed.
  Tasks 12.5a-12.5c are complete; Task 12.5 remains open for direct user acceptance and Task 12.6
  remains open for separate Cutover authorization.

## S12D answer-quality and interactive-latency repair — 2026-07-28

- Direct feedback clarified that retrieval evidence is an input to final LLM presentation, not the
  user-facing answer format. The shared prose prompt previously omitted the user's question, so it
  could only restate selected claims. The `canonical-v2-prose-v2` prompt now receives the current
  question, answers it first, merges repeated facts, avoids projection field labels, and retains the
  same evidence-only factual boundary across Professor, Company, Paper, and Patent.
- The current question is transient process-only input on `TurnResult`; it is excluded from model
  serialization. Public responses still contain no raw evidence or trace payload. The public UI
  continues to default-collapse `查看依据` and exposes only validated official URLs.
- The latency regression was systemic rather than Ding-Wenbo-specific: each turn rehashed immutable
  release authority, reread/reparsed 3,784 lookup documents across sibling lanes, lazily audited the
  4,338-point vector snapshot on the first request, and allowed the provider client to wait beyond a
  useful interaction budget. Release composition now caches immutable addresses and one audited
  lookup view, invalidates physical-document reuse on file fingerprint changes, warms the reusable
  vector snapshot during startup, and enforces a 12-second application wall-clock prose budget with
  a fixed four-worker executor and no SDK retries.
- Real HTTP on the final `0.0.0.0:18188` process returned 200 and `llm_synthesized` for the Ding Wenbo
  profile in 8.26 seconds, its founder follow-up in 7.05 seconds, and the Wujie Zhihang Company
  profile in 2.91 seconds. The founder answer states that Ding Wenbo participated in founding Shenzhen
  Wujie Zhihang Technology Co., Ltd.; the Company answer uses two organized paragraphs with no
  `简介` or `技术路线` field labels. The Professor citation is only the official Tsinghua homepage;
  public `evidence` remains empty.
- Focused verification reports serving `36 passed`, answer grounding/closure `28 passed`, vector and
  internal-reference regressions `2 passed`, Admin HTTP `16 passed`, and public UI `11 passed`.
  Changed-file Ruff/format and targeted Pyright are clean. Strict OpenSpec validation and
  `git diff --check` pass.
- Browser checks at desktop and 390px mobile widths found no horizontal overflow or message overlap.
  The evidence disclosure begins closed, expands successfully, links only to
  `http://www.sigs.tsinghua.edu.cn/dwb/main.htm`, and renders no `/browse` text.
- Remaining risk: final Candidate process startup still takes about 16 minutes and peaks near 9.5 GB
  because it replays and audits the complete serving envelope before listening. This cost is outside
  individual request latency and remains a separate startup-path optimization opportunity. A timed-
  out provider job may occupy one of the four fixed prose workers until the provider returns, but it
  cannot hold the HTTP request beyond the configured wall-clock budget.
- No source/canonical/index bytes, active pointer, production resource, commit, Push, PR, promotion,
  archive, cleanup, or Cutover changed. Task 12.5 remains open for direct user acceptance and Task
  12.6 remains separately authorized only for a future Cutover decision.

## S12D end-to-end TTFT diagnosis and transport reuse — 2026-07-28

- Here TTFT is measured from browser query submission until answer text is visible, not provider
  token TTFT. The current page awaits the complete `/api/chat` JSON before rendering, so HTTP
  `time_starttransfer` equals total backend completion time. A syscall trace of a representative
  3.599-second request attributed about 2.70 seconds to Serper, 0.67 seconds to final LLM prose, and
  about 0.23 seconds to local planning, retrieval, validation, mapping, and checkpoint work.
- The shared Web adapter previously constructed a new `WebSearchProvider` and HTTP session on every
  turn. Direct real-provider calibration measured repeated new transports at 1.64-2.08 seconds and
  a reused keep-alive transport at 1.15-1.24 seconds for the same query. The adapter now constructs
  the provider once per loaded serving runtime; query text, request bounds, provider parameters,
  result filtering, evidence admission, reranking, and LLM synthesis are unchanged.
- Before the repair, the second four-domain HTTP round took 3.685, 3.883, 3.169, and 3.402 seconds
  (mean 3.535 seconds). After restart, the same warm round took 2.134, 1.502, 2.184, and 1.567 seconds
  (mean 1.847 seconds, 47.8% lower). All eight post-restart answers remained `llm_synthesized`, had
  non-empty answer text, exposed `evidence=[]`, and retained the existing official-citation policy.
- Browser DOM timing showed the Wujie Zhihang Company answer at 1.674 seconds. A separate Ding Wenbo
  browser turn took 11.214 seconds while still returning the same 298-character synthesized profile,
  a closed `查看依据` disclosure, and only the official Tsinghua homepage. A following traced Ding
  request completed in 2.794 seconds, with about 1.74 seconds in Web and 0.86 seconds in LLM prose.
  This confirms material upstream Web tail variance remains even after connection reuse.
- The 10-second universal-Web outer budget was not shortened: doing so can discard slow but valid Web
  augmentation and would violate the output-preservation constraint. Raw LLM token streaming was
  also not introduced because the current complete-answer validation rejects structured/internal
  values before public rendering; streaming before that gate would change the safety contract for a
  maximum normal-path gain of only the roughly 0.6-0.9-second prose stage.
- Regression verification: serving reports `36 passed`, answer grounding/closure `28 passed`,
  lookup/vector cache regressions `2 passed`, and Admin HTTP/UI `27 passed`. Focused Ruff passes,
  targeted Pyright reports zero errors, strict OpenSpec validation and `git diff --check` pass. The
  restarted Candidate is listening on `0.0.0.0:18188` and the public page returns HTTP 200. Startup
  still takes about 16 minutes and peaks near 9.5 GB, which is outside per-query TTFT and remains a
  separate optimization opportunity.
