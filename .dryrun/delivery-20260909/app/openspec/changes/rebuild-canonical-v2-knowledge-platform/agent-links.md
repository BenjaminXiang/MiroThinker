# Agent and Slice Links

## Ownership

- OpenSpec owns behavior, scope, acceptance, and verification intent.
- Each slice has one active writer.
- Direct user evaluation owns final Candidate-to-Accepted promotion for the remaining milestone.
- The primary agent may delegate bounded work to subagents. Parallel writers use isolated
  branches/worktrees and separately named disposable resources; subagents do not approve an entire
  task, push, promote, or mutate shared active pointers.
- Remaining tasks are integrated as one lean end-to-end milestone. No commit is created without
  explicit user authorization.
- Recovery exception: the final bytes accumulated between 2026-07-13 and 2026-07-21 were never
  committed and their intermediate blobs do not exist. By explicit user decision on 2026-07-22,
  those bytes are imported once as an aggregate S11 baseline after an exact recovery snapshot. The
  import is not represented as reconstructed task history; the original slice contracts and
  receipts remain the historical evidence.

## 2026-07-26 lean E2E rebaseline

This section supersedes conflicting open-task dependencies in the historical DAG below. It does not
rewrite Accepted implementation history.

- Task 2.8 and its contract/exclusion/blind-calibration review workflow are retired. Existing review
  code, ledgers, packets, and receipts remain non-normative historical artifacts and are not run.
- Tasks 8.1, 8.8, and 9.8 are retired as separate aggregate gates. Their useful implementation and
  regression tests remain available, but no reviewed claim-level corpus or calibrated judge unlock
  is required.
- Task 12.2 owns the serviceable four-domain isolated Candidate and content-addressed read-only
  serving bundle. Task 12.3 owns representative smoke coverage plus the real-runtime replay of all
  17 workbook conversations/25 turns. Task 12.4 owns only the minimal checks named in
  `acceptance.md`. Task 12.5 is direct user acceptance; Task 12.6 retains the separate cutover gate.
- `docs/测试集答案.xlsx` is the customer benchmark Ground Truth. Missing support is a product gap,
  never a reason to exclude a case. Workbook answers cannot be loaded or hardcoded into runtime.
- Independent slice review, scaled human labeling, LLM-judge calibration, repeated broad suites, and
  duplicate evidence envelopes are not required for the remaining milestone.

## Slice dependency DAG

The following is retained as historical execution context. The lean E2E rebaseline above governs all
remaining work. S1 through aggregate S6 are Accepted at their recorded historical contracts:

- S2C/tasks 2.7-2.8 migrates the acceptance oracle to claim-level case contracts and must be Accepted
  before S8/S9 acceptance execution.
- S6R/tasks 6.9-6.11 reconciles internal Person/Technology catalog, identity, and projection
  boundaries while retaining four public domains and answer-scoped Product capability. S6R1-S6R5
  and Tasks 6.9-6.11 are Accepted. S7A/Task 7.1, S7B/Task 7.2 KnowledgeBuild, S7C/Task 7.3 typed
  candidate projection, S7D/Task 7.4 index RED, and S7E/Task 7.5 isolated lookup/vector index
  construction plus S7F/Task 7.6 reconciliation and ReleasePublication are Accepted. S7G froze the
  exact three-scenario Task 7.7 RED; S7H made it GREEN on fresh isolated DB/index targets. Task 7.7
  and aggregate S7 are Accepted. S2C1 RED and S2C2/Task 2.7's strict validator plus complete 52-case
  draft migration are Accepted at 47/80. S2C3A's exact five-group oracle RED is also Accepted;
  S2C3B's mechanical evaluator/recorded-fake GREEN and S2C3C1's deterministic unapproved external-
  review packet are Accepted. The historical two-human S2C3C2 contract is Rejected/Superseded; the
  replacement single-human review workbench is In Progress and awaits attributable human 29+23+60
  decisions, judge authorization, and sealed calibration. Task 2.8 remains open and owns
  reviewed-corpus application, aggregate acceptance, and the S8/S9 oracle unlock.
- KnowledgeBuild candidate construction and the pure four-public/three-internal projection bundle
  are implemented together with deterministic lookup/vector builders and the first isolated full
  rebuild. Task 7.4 freezes index and point-parity obligations; accepted Task 7.5 owns construction
  only, and accepted Task 7.6 owns pure snapshot reconciliation/verification/promotion/rollback.
  S7G freezes Task 7.7's real isolated DB/index parity, guarded pointer adapter, and physical
  rollback-rehearsal contract; Accepted S7H owns its package-internal GREEN adapter and execution
  receipt. S7I then re-Accepts the narrow lookup-document lineage seam: exact eligibility decision,
  outcome, limitations, and complete-document manifest binding are retained without changing the
  formal ledger. S8L1 consumes that corrected document only through a release-bound physical
  bundle. Production alias/cutover remains outside these slices and is not authorized by S7.
- S8 fixture-only RED tasks without their own reviewed-corpus predecessor may start against
  synthetic typed fixtures after the applicable Accepted S6R/S7 seams. Task 8.1's reviewed-case
  calibration and all S8/S9 claim-level acceptance-oracle execution still await Accepted S2C;
  fixture RED is not an accepted substitute. Task 8.2 and every executable local retrieval path
  consume an Accepted S7 release, typed relationship/eligibility/reference catalog, and index seam.
  S8W/Task 8.4's three-group Universal-Web/skip/official-safety/failure RED and S8S/Task 8.6's
  three-group sufficiency/enumeration/bounded-supplemental RED are Accepted at the global 52/80
  ledger against synthetic adapters without claiming real-provider or S8 runtime acceptance. S8Q1's
  four-group taxonomy/safety/enumeration, protected-rewrite/institution, injected-ambiguity, and
  internal Person/Technology fixture RED predecessor is Accepted at the unchanged global 54/80
  ledger without checking Task 8.1 or substituting for reviewed calibration. S8RF's three-group
  seven-lane/candidate-trace, late-fusion/rerank, and Web-handle lifecycle fixture RED predecessor is
  also Accepted at the unchanged ledger without checking Tasks 8.3/8.5. S8RG's atomic synthetic
  KnowledgeRead mechanics GREEN is Accepted at the unchanged ledger: the two atomic boundary groups
  plus all 14 read owners are GREEN through one deep module, including bounded supplemental budget/
  lane validation, full trace for server-limited candidates, and the re-Accepted optional
  continuation-coverage successor shape. This does not substitute synthetic
  mechanics for reviewed calibration, real-provider/runtime evidence, or claim-level oracle
  execution. S8L1 is Accepted as the first real physical local-read predecessor: it binds exact
  lookup to a serviceable `PublishedRelease` plus exact `IsolatedReleaseBundle` snapshot and retains
  typed local/eligibility lineage without checking Task 8.3. S8L2 adds the release-bound structured
  displayed-set consumer over the same guarded snapshot, preserves legacy exact identities, and
  rejects cross-lane trace wiring without checking Tasks 8.3/8.5. S8P1 is Accepted as the first
  release-bound planning predecessor: it exact-replays that S7 graph, validates the release catalog/
  policy, derives internal Person/Technology planning records, and content-binds the resulting plan
  without checking Task 8.2. S8P2 is Accepted at `56/80`: it closes Task 8.2 with a finite recorded-
  proposal taxonomy/safety matrix, server-owned official-Web policy and budgets, material-part
  capture, and one lightweight open assessment intent while preserving S8P1 identities. Tasks 8.1,
  8.3, 8.5, and 8.7-8.8 remain open. S8E1 is Accepted at the unchanged `56/80` ledger as the
  release-bound Task 8.3 composition predecessor: it hides the physical exact/structured adapters,
  accepts only bounded Universal-Web/snapshot ports, and fails cross-wired plan/release binding or
  unsupported lanes before effects. S8L3 is now Accepted at the same ledger as the first real
  lexical successor: it performs bounded normalized substring recall over guarded typed public
  projection content with distinct lexical lineage. S7J is also Accepted at the unchanged ledger:
  public vector points now carry exact semantic decision effects and builder/release parity shares
  one full-envelope point hash, clearing the mandatory S8V1 prerequisite. S8V1 is now Accepted at
  the unchanged ledger: its optional release-owned vector adapter audits the complete physical
  snapshot, performs bounded deterministic cosine recall, and authority-validates every returned
  vector trace. S8V2 is also Accepted at the unchanged ledger: a finite recorded selector chooses
  Professor identity/research/both points, lookup-derived display authority remains release-bound,
  and post-delegate view/name validation fails closed. S8IR1 is Accepted at the same ledger: paired
  replay authority now executes exact Person filters and Technology route definitions while every
  displayed identity remains a replayed public object and relationship state remains unavailable.
  S7K is now Accepted as the narrow relationship-publication correction: one optional exact
  relationship request/result pair binds the combined-registry/internal graph, seven release
  projection manifests, relationship section, and complete build-manifest hash before any effect.
  Legacy no-pair zero bundles are explicitly non-authoritative. S8R1 is now Accepted at the same
  ledger: the exact Technology-route-to-Company family executes three Product-to-Technology states
  from that release authority, retains Product-scoped claims and Company locator identity, and does
  not reopen physical relationship storage or propagate Product capability. S8R2 is also Accepted
  at the same ledger: one protected displayed Company reverse-traverses exact accepted Patent-
  applicant authority to fully traced Patent results, while unrelated Web evidence cannot own the
  Company witness and legitimate same-Patent Web evidence may coexist. S8R3 is also Accepted at the
  same ledger: one protected displayed Professor forward-traverses exact accepted current
  attribution authority to fully traced Paper results, with Paper-scoped Web constraint isolation,
  honest open-world coverage, and path/lane rejection before effects. S8R4 is also Accepted at the
  same ledger: one protected displayed Paper inverse-traverses that exact authority to fully traced
  Professor results while preserving the Canonical Professor-to-Paper claim, post-filter result
  cap, and Accepted Web alias semantics under finite identity-state validation. S8R5 is also
  Accepted at the same ledger: one protected displayed Patent traverses exact applicant-only
  authority to fully traced Company results, with authoritative-count replay before caller caps and
  the same finite Web identity boundary. S8C is Accepted at `59/80`: one public release-bound
  `KnowledgeRead` executes all seven lanes, forwards the accepted fusion/rerank/sufficiency/
  supplemental/handle ports, and admits exact-release/exact-session read-only handle replay. Tasks
  8.3/8.5/8.7 are closed. The replacement Task 2.8 single-human review workbench still gates only
  Tasks 8.1/8.8 reviewed calibration and claim-level aggregate acceptance, not independently
  executable S9 implementation work.
- S9 answer/session RED contracts may start against typed evidence fixtures; production answer and
  session behavior consumes the Accepted S8 evidence/trace result. S9A/Task 9.3's three-group
  evidence-based AssessmentFrame RED and S9M/Task 9.5's four-group Canonical/Web session,
  ambiguity, continuation, and topic-switch RED are Accepted. S9G/Task 9.1's four-group exact
  claim/citation, direct Product-capability, derived Industry-Brief/coverage, and deterministic-
  fallback RED is also Accepted at the global 54/80 ledger without claiming S8 or S2C oracle
  execution. S9AG's atomic synthetic KnowledgeAnswer mechanics GREEN is Accepted at the unchanged
  ledger: all 13 S3A/S9A/S9G/S9M/trust-boundary owners are GREEN through one deep module, including
  fail-closed session rollback, suppression-aware Product handling, and first-turn unresolved-Web
  traversal refusal. S9C1 closes Task 9.7 at 55/80 by validating the exact executable option
  combinations, neutralizing caller labels, and enforcing traversal-only relationship types while
  preserving every accepted next-turn binding. S9I is Accepted at `62/80`: it closes Tasks
  9.2/9.4/9.6 with complete structured claim/conflict/inference binding, sanitized rendering,
  answer/assessment traces and degradation, evidence-relevant free per-turn assessment, typed
  release/session referents, bounded server-owned safety guidance, and one real Read-to-Answer
  vertical owner. This does not substitute for reviewed claim-level/provider/latency acceptance;
  Task 9.8 and aggregate S9 remain open.
- S10A/Task 10.1's three-group gap-trigger RED is Accepted at 48/80 against shared typed gap/trace
  fixtures. S10B/Task 10.2's pure typed gap creation and bounded recorded-classifier GREEN is
  Accepted at 49/80 without claiming upstream query/answer execution. S10C's three-group synthetic
  offline-remediation/accepted-release-plus-effect RED predecessor is Accepted at the unchanged
  global 54/80 ledger. S10D's pure content-bound lineage/transition/replay mechanics GREEN is also
  Accepted at the unchanged ledger. S10O is Accepted at `65/80`: it closes Tasks 10.3/10.4/10.5
  with append-only durable gap/remediation storage, exact Accepted release/manifest/effect closure
  truth, bounded V2-only admin operations/UI, and online/offline no-canonical/index-write owners.
- S11A is Accepted at the unchanged `65/80` ledger. The registered chat route uses one explicit
  release-bound V2 planner/Read/Answer adapter with typed continuation/session state, bounded trace,
  atomic compatibility mapping, and a read-only immutable feedback checkpoint; legacy SQL remains
  only an unregistered comparison oracle. Receipt SHA-256:
  `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`. S11B consumed this
  checkpoint; Tasks 11.1-11.5 remained open at that historical S11A checkpoint.
- S9J is an Accepted successor correction over Accepted S9I plus historical Accepted S11A; it does
  not rewrite the historical S11A receipt or call corrected live hashes a rebaseline. Public answer
  copy excludes SHA/typed IDs/raw enums, while exact structured audit/continuation data remains and
  material missing/conflicting outcomes carry both typed limitations and bounded gap sentences.
  Receipt SHA-256:
  `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`. The ledger remains
  `65/80`; S11B bound this receipt as successor authority, while Tasks 11.1-11.5 remained open at
  that historical checkpoint.
- S11B is Accepted at the unchanged `65/80` ledger. Its candidate admin/UI/feedback and three
  explicit CLI surfaces use only release-bound Canonical V2 interfaces; exact route/import/script/
  inventory guards quarantine legacy V042, direct retrieval/SQL, global readiness, and old-index
  paths. Receipt SHA-256:
  `cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945`. Tasks 11.1-11.5 remained
  open at that historical S11B checkpoint.
- S11C is Accepted at `70/80` and atomically closes Tasks 11.1-11.5. Exact predecessor reruns,
  interface/trace/claim-level/PostgreSQL/release-index owners, immutable legacy disposition, broad
  JUnit/failure reconciliation, execution provenance, generated cleanup, and independent evidence/
  protected-scope reviews all pass with zero open Critical/Important findings. Receipt SHA-256:
  `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`. S12A/Task 12.1 is next.
- The 2026-07-22 S11 consolidation preserves all accumulated bytes at recovery commit
  `8fd5f26c0749599860d4a08a26e6a9694d05a017` and imports the formal final state at
  `641278f01b005c66bd356533d4df0fd11b678394`. Relocation correction
  `438c715190d4f8b5c2bbf9f29b6abe3899ec2330` preserves frozen S11C provenance while allowing the
  same raw-hash-bound evidence to validate from the clean checkout. Baseline verification passed;
  this consolidation branch is the sole parent for later Ready slices. `main` remains `f0e6224`.
- S11 consumer migration depends on the replacement deep modules it migrates to being Accepted.
- S12 candidate construction and final acceptance depend on all required build, release, index,
  query, answer, gap, and consumer seams being Accepted.

Two or more tasks may be In Progress when their dependencies are Accepted or their consumed
interfaces are frozen, their writers and resources do not overlap, and each remains independently
testable and commit-scoped. If a shared contract, migration head, database, Milvus release, output
directory, or active pointer would have multiple writers, that seam returns to serial integration.

## Git mainline promotion gate

The user selected aggregate S6 acceptance as the checkpoint for moving Git `main` to Canonical V2.
Promotion is fast-forward-only and requires all of the following in the execution session:

1. Task 5.7/S5G and Tasks 6.1-6.8 are Accepted with linked review/verification evidence. Later S2C/
   S6R requirements do not rewrite the historical promotion checkpoint or authorize S7+ execution.
2. The V2 integration worktree is clean and contains no untracked implementation/evidence required
   by the accepted checkpoint.
3. Every Canonical V2 side branch has been integrated, proven redundant, or explicitly abandoned;
   no unique accepted patch remains outside the integration line.
4. The root worktree's unrelated dirty files are preserved and reconciled without overwrite.
5. `git merge-base main <v2-integration>` still equals `main`; ahead/behind inspection proves a pure
   fast-forward, with no merge or rebase.
6. Strict OpenSpec, aggregate S6 checks, frozen-source safety, and diff/secret/scope checks pass on
   the exact promotion commit.

Meeting this gate does not authorize database/index promotion, production-like cutover, push, PR, or
archive. If any condition fails, Git `main` remains unchanged.
