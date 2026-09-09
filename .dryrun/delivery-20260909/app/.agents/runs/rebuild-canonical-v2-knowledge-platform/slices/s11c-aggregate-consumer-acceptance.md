# Slice Contract: S11C Aggregate Consumer Acceptance

## Status

**Accepted** at `2026-07-21T19:10:41Z` after Candidate at `2026-07-21T19:05:17Z`. The former Ready authorization at
`2026-07-21T15:02:07Z` remains superseded. The execution re-authorization at
`2026-07-21T17:42:54Z` was itself superseded for Candidate progression when final evidence review
found one Important traceability gap: four predecessor reruns lacked exact execution cwd, and the
two guarded broad runs lacked machine-validated UTC execution windows. The gap is now closed by a
v2 predecessor receipt plus a raw-hash-bound JUnit provenance supplement. Focused/full validators,
capture owners, static checks, independent evidence review, generated cleanup, and protected-scope
review are GREEN at `Critical=0 / Important=0`. The final receipt is
`s11c/verification-receipt.json`. Tasks `11.1`-`11.5` closed atomically; the formal ledger moved
`65/80 -> 70/80` with no other task change.

The reviewed repair hashes are validator
`3924a00af6dbe183f0a1199ed7b9977b5475dad3ee558b4fa4fd7758f9ca62bb`, capture helper
`a1bbf4d60ee2e73aee93a27ff3d75a6d94526f08d4701c243c40ca204da7bdf4`, capture owner
`060c7ab2979bb9d69b6a30533660205d226ef5bb660cd62897616ddff171db8c`, guarded provenance
`8b307160f9f1231896d11f43d71b06daed329824a50f3255a127d922aa35f467`, preserved v1 predecessor
receipt `84507b7c3fd6a441547922cfc7012c58a74b6a11c82ec001ffe8e300ffc5eb11`, and authoritative v2
predecessor receipt `6043e991ff2971aba8bb5a1492261be302412aab1cb272b9027ac24009282d8d`.

The earlier reviewed pre-authorization hashes remain historical execution evidence: contract
`6b6b045d136245a688448dc71570a3c23b2ab7252bb549b690ba39516f8c5a3a`, audit
`2669b4129ae162ca3510438d576c28da30cb1a3534feb1a87c9d29ce2392cfa8`, plan
`a54b96d5f882c09a3c2defc2f1567b3b8e5e7d8eabd568866dba4e53374ad44e`, wrapper
`31aee4c517e09f6b7a40413a8949b285df35f9032b78e126c94b675fb3867ed1`, wrapper owner
`f70855fa251c18d6e6b3cfed9871ee09cd994ba3fe07cd0525bae5373b1d606d`, and validator
`647f04c8ecf05ae0a9ce9316ea96a088db0fcf7ef2df90c54ac60deec949b81c`.

One duplicate non-authoritative rerun attempt followed an orchestration-session ambiguity. It ran
the same effect-free pytest commands, reached the exclusive-create `FileExistsError` after the
authoritative v2 receipt existed, created no receipt, and overwrote no v1/v2/broad/predecessor
artifact. It is not acceptance authority.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
- OpenSpec tasks: `11.1`, `11.2`, `11.3`, `11.4`, and `11.5`; all five are Accepted and changed
  atomically from unchecked to checked at `2026-07-21T19:10:41Z`.
- Requirement sources:
  - Task 11.1 — migrate sanctioned consumers to deep-module interfaces;
  - Task 11.2 — interface/scenario/trace-replay/real-PostgreSQL/index-adapter evidence plus accepted
    claim-level case contracts rather than prose gold;
  - Task 11.3 — remove or quarantine V042/direct-SQL/fixed-handler/global-readiness/old-index paths;
  - Task 11.4 — explicit safe-target broad checks and separate retired/unrelated failure accounting;
  - Task 11.5 — independent acceptance that no valid behavior depends on a removed implementation
    detail.
- Depends on: historical Accepted S11A, Accepted S9J as the explicit authority for its corrected
  live service/owner bytes, and Accepted S11B, including exact final receipt hashes.
- Structural evidence dependency: Accepted S2C2 / Task 2.7 only.
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/dependency-audit.md`.
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/implementation-plan.md`.

## Goal

Accept the complete S11 consumer boundary without adding production behavior:

```text
Accepted S11A chat/session + Accepted S11B admin/browse/feedback/CLI/quarantine
  + frozen Accepted S11B inventory authority
  + separate complete S11C disposition overlay
  + exact interface/scenario/trace/PostgreSQL/release-index owners
  + exact broad JUnit/nodeid/failure-signature ledger
  + independent C0/I0 review
  -> Tasks 11.1-11.5 accepted atomically
```

Every sanctioned path must be Canonical V2; every retired path must be linked to a passing
replacement/quarantine owner; every broad failure must remain visible and exactly reconciled. S11C
does not make a failing accepted behavior pass by editing production, weakening tests, or changing a
predecessor contract.

## Required behavior

### Accepted predecessor binding

- Historical S11A, successor S9J, and S11B contracts/receipts are Accepted before S11C becomes
  Ready. Historical S11A hashes remain immutable evidence, but live-byte checks use the latest
  Accepted owner per path: every path listed in S11B `implementation_artifacts` must match S11B;
  an S9J-corrected path not superseded there must match S9J; only remaining S11A paths compare to
  historical S11A. No predecessor receipt is rebaselined.
- S11C reruns the final S11A/S11B public-owner commands unchanged. Each exact rerun has an S11C-local
  receipt binding the Accepted receipt path/hash/pointer, authority representation, cwd, sanitized
  environment delta, UTC time, real exit code, and raw stdout/stderr hashes. Parameters are not
  injected into an Accepted command. Where the Accepted authority is a string rather than an argv
  array, S11C binds that exact string/hash plus the actual child argv instead of inventing historical
  token authority. Any regression is a stop condition, not authorization to edit a predecessor.
- Broad JUnit separately cross-proves each applicable predecessor owner by exact run ID, nodeid,
  raw JUnit hash, and passing outcome. A CLI/script owner outside the broad collected universe is
  proven by its exact rerun receipt unless used as a retired replacement owner, in which case an
  additional recorded-JUnit pass is mandatory.
- The aggregate validator preserves and raw-hash-binds `s11c/predecessor-reruns-v1.json`, but
  machine-consumes `s11c/predecessor-reruns-v2.json` as the current authority. V2 resolves each of
  four commands from the Accepted S11B receipt JSON pointer, requires exact repository-root cwd,
  exact launcher argv, sanitized environment delta, strict UTC start/finish, real
  exit/stdout/stderr hashes, and every applicable passing ledger-JUnit cross-link. The two Accepted
  `tests/scripts` owners remain exact-receipt-only unless used as a retired replacement owner.
- The final receipt maps each of Tasks 11.1-11.5 to exact commands, nodeids, artifacts, and hashes.

### Immutable inventory and separate disposition overlay

- The Accepted S11B receipt is the sole authority for inventory path, raw-byte SHA-256,
  category/disposition counts, and exact sorted `s11c_disposition` entries/count.
- S11C records the exact Accepted S11B receipt hash and the exact JSON pointer containing the
  inventory hash. It verifies raw bytes still match, but never edits, reserializes, canonicalizes,
  regenerates, reclassifies, or accepts a replacement inventory/version/hash.
- S11C dispositions live only in `s11c/disposition-overlay-v1.json`. The overlay is bound to the
  Accepted receipt/hash and covers every base `s11c_disposition` `(top-level category, path/module)`
  key exactly once with no extra key; S11C invents no new inventory ID field.
- Overlay dispositions are only `replaced_owner_passed` and `reference_only_quarantined`. Every
  entry names at least one exact pytest nodeid that passes in recorded JUnit.
- `reference_only_quarantined` uses an import/route/command boundary owner as its replacement proof;
  it is not a prose-only waiver.
- A retired ledger row normally binds the same exact inventory key directly to the frozen base
  disposition: base `replaced` maps to `retired_replaced`, and base `reference_only` maps to
  `retired_reference_only`. Only a base entry whose frozen disposition is `s11c_disposition` uses
  the overlay, where `replaced_owner_passed` and `reference_only_quarantined` map respectively to
  those two retired dispositions. Both paths still require an exact passing recorded-JUnit owner.
  The overlay never duplicates or reclassifies an already-final base disposition.

### Exact broad-result reconciliation

- A reviewed S11C-local wrapper installs the Accepted S11B early no-external guard before initial
  conftests, clears the same 49 sensitive names, blocks socket/psycopg/dotenv effects, records
  guard/cleanup receipts, and applies signature v3. Admin collect/run uses exact marker
  `not requires_classifier_llm` and records only the classifier benchmark as deselected. Naked broad
  pytest is not acceptance evidence.
- Each required broad command records exact argv, exit code, safe target identity,
  collected-nodeid bytes/hash, and raw JUnit XML bytes/hash. The immutable broad artifacts are
  supplemented by `s11c/guarded-execution-provenance-v1.json`, which raw-hash-binds the guarded
  receipt, failure ledger, and each JUnit and strictly derives UTC start/finish from that JUnit's
  exact `testsuite timestamp + duration`. The aggregate validator recomputes the derivation.
- The guarded wrapper captures exactly two ledger-input partitions: complete no-external Admin and
  all discovered Canonical V2 predecessor files except the exact S11C acceptance file. The validator
  consumes only artifact paths declared by the ledger; it never globs an evidence directory. The
  ledger binds the raw S11C guarded-wrapper receipt SHA-256.
- The guarded receipt run set is exactly those two partitions. The ledger may additionally contain
  Task 11.2 targeted owner runs; every non-guarded run must exit `0`, contain only passing JUnit
  cases, and can never contribute a failure/disposition row.
- After overlay and ledger completion, the focused S11C owner runs once in a separate
  `s11c/focused/` namespace that is excluded from validator inputs. A post-process receipt, written
  only after that pytest process exits, proves focused `1 passed` with no skip/xfail/XPASS and proves
  that predecessor files plus the focused file are the exact discovered Canonical V2 union. No
  immutable broad artifact is overwritten; a fresh attempt uses a new attempt ID/root.
- Every JUnit failure/error maps uniquely to one exact collected pytest nodeid and exactly one
  retired-failure-ledger row. Every ledger row maps back to one JUnit failure/error.
- Baseline signature schema `canonical-v2-s11b-baseline-signature-v3` preserves exception type,
  JUnit message, traceback/assertion body, filenames, line numbers, IDs, and values. It normalizes
  only line endings, the guard receipt's exact effective run basetemp root to `<pytest-tmp>/` first,
  and the exact repository root to `<repo>/` second, then hashes
  `outcome + LF + normalized message + LF + normalized body`.
- The declared command `--basetemp` remains independently validated as exact argv evidence. The
  effective signature root is bound from `guard_preflight.pytest_temp_roots[run_id]["run"]` and the
  matching terminal child receipt; cleanup, owned-root containment, session completion, and
  unconfiguration must all be true. Declared and effective roots are intentionally distinct because
  the Accepted S11B guard overrides pytest's runtime root.
- A failure disposition is only `retired_replaced`, `retired_reference_only`, or
  `unrelated_preexisting`. Retired rows require the matching frozen-base or overlay category/path key
  under the mapping above and a passing owner nodeid. Unrelated rows have no inventory key and
  require an exact unchanged baseline
  signature already frozen by Accepted S11B evidence, a passing named non-consumer scope owner, and
  independent acceptance. Without that frozen baseline the disposition is unavailable.
- An S11/candidate import/route, public contract, evidence trace, release/index parity,
  target-safety, no-online-write, or replacement-owner failure cannot be marked unrelated.
- No unaccounted failure, changed signature, missing replacement pass, duplicate/missing row,
  collection error, glob waiver, known-failure list, skip/xfail insertion, `-k not`, `--ignore` of a
  predecessor, swallowed exit code, or assertion weakening is allowed.

### Task 11.2 evidence

- Accepted S2C Task 2.7 structural owners run and preserve exact machine-judged required/forbidden
  claims/entities, allowed variants, snapshot/as-of, coverage policy, stage expectation, and content
  identity contracts. Reference prose remains non-normative.
- Public interface, scenario, and trace-replay owners run through accepted deep-module seams.
- Real PostgreSQL owners run only against the fixed S11C-local database
  `miroflow_canonical_v2_s4c_disposable`, newly created inside the already-Accepted marker-owned,
  network-none/no-published-port disposable container and recorded in
  `s11c/disposable-postgres-target-receipt.json`. Creation fails closed if that database already
  exists. The exact destructive marker and Accepted backup gate are verified before tests; only the
  four `CANONICAL_V2_TEST_*` values reach the test process, and no credential-bearing DSN is stored
  in evidence. Cleanup is authorized only if this attempt created the database and its exact marker
  still matches; final absence is recorded. Generic/original/production-like targets fail before
  connect/write.
- The aggregate validator machine-consumes the lifecycle receipt and cross-binds its Accepted S10O
  authority, owned container/base/target identity, exact four environment names, `122` passing
  owner cases/JUnit hash, cleanup proof, and final target absence to ledger run
  `disposable-postgres`.
- Release-publication and release/index-projection owners prove exact release/index parity,
  release-bound adapters, rollback authority, and zero direct active-index/original-Milvus mutation.
- S2C Task 2.8 external human review, prose/reference-answer judgment, LLM calibration, and
  real-provider quality acceptance are not required by S11C and do not block it.

### Pure acceptance and atomic closure

- S11C changes no production implementation, existing test, schema, migration, Accepted predecessor,
  inventory, source, index, active pointer, or runtime configuration.
- The sole database-content exception is the exact S11C-owned transient target described above;
  it uses the accepted explicit target gate and is removed with an exact final-absence proof.
  Disposable index fixtures remain test-local and are cleaned up.
  Original PostgreSQL/Milvus/forensic sources and remote Git state remain exact.
- Candidate status requires all evidence but changes no task. Accepted status additionally requires
  one independent review with zero open Critical/Important findings.
- At acceptance only, Tasks 11.1-11.5 change from unchecked to checked in one atomic evidence update.
  The exact live ledger before/after has delta `+5`; partial closure is forbidden.

## Non-goals

- No new feature, API, route, UI, storage, migration, adapter, builder, provider, evaluator,
  compatibility mapper, retry, scheduler, or framework.
- No repair of an S11A/S11B regression, production defect, Accepted contract, or historical test.
- No deletion/movement of legacy trees; the Accepted inventory and overlay provide bounded
  quarantine/disposition evidence.
- No S2C Task 2.8 external-human oracle, prose-gold matching, real-provider quality/latency/cost
  acceptance, or claim that S2C is globally Accepted.
- No S12 candidate build, final product acceptance, user acceptance, promotion, production-like
  Cutover, archive, or destructive cleanup.
- No Commit, Push, PR, source write, original-source read/write activation, or active pointer change.

## Allowed scope

- Create `apps/miroflow-agent/tests/canonical_v2/test_consumer_acceptance_contract.py` as the sole
  application-tree test/implementation delta.
- Create
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/capture_guarded_partitions.py` and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/test_capture_guarded_partitions.py` as
  the S11C-local evidence-capture wrapper and its fail-closed owner. They may only reuse and verify
  the Accepted S11B no-external guard contract; they are not product/runtime code, do not enter
  application script discovery, and do not change an Accepted predecessor artifact.
- Create
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/capture_execution_traceability.py` and
  `test_capture_execution_traceability.py` as the evidence-only, exclusive-create capture helper
  and owner for the JUnit provenance supplement and predecessor v2 receipt. They may not overwrite
  v1, a broad artifact, or an existing supplement/v2 receipt.
- Create only the authorized wrapper/owner plus S11C-local overlay, ledger, collected-nodeid, JUnit,
  exact-rerun, focused, postflight, disposable-target, review, and receipt evidence under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/`.
- Create and later remove only the exact S11C-owned transient PostgreSQL database authorized under
  Task 11.2; no other database/container state may change.
- Update this contract and the S11C audit/plan before acceptance.
- At final acceptance only, update the authorized existing OpenSpec tasks/acceptance/change-log/
  agent-link and verification/portfolio/convergence pointers needed to record S11C and the atomic
  five-task ledger transition.

## Forbidden changes

- Any production file or existing test; any S9, S10, S11A, S11B, S12, S2C, inventory, Accepted
  receipt, schema, migration, provider, source, active-pointer, or database/index-content edit other
  than the exact authorized S11C-owned transient PostgreSQL target.
- A new inventory version/hash, edit to an Accepted inventory entry, overlay entry for an unknown
  base category/path key, unresolved/duplicate overlay entry, or a disposition without an exact
  passing owner.
- A ledger row without exact JUnit/collected-nodeid/signature identity; manual known-failure lists,
  broad regex signature erasure, output-only summaries, or prose justification without artifacts.
- Running PostgreSQL checks through generic `DATABASE_URL`/`DATABASE_URL_TEST`, original `pgtest`,
  an unmarked database, a missing backup gate, or any production-like target.
- Treating a failed accepted public behavior, candidate path, write-safety invariant, release/index
  parity owner, S11 owner, or changed signature as unrelated/retired.
- Depending on S2C external human review or prose reference answers to accept Task 11.2.
- Checking only a subset of Tasks 11.1-11.5, checking any task before Candidate evidence and final
  independent `C0/I0`, or changing another OpenSpec checkbox.

## Expected unchanged behavior

- Accepted S1-S11B public contracts, serialized shapes, runtime behavior, exact inventory bytes, and
  verification receipts remain unchanged.
- S11A remains the only release-bound chat/session owner. S11B remains the only candidate admin/UI/
  feedback/CLI/quarantine implementation owner. S11C only verifies their aggregate boundary.
- Task 2.7 remains Accepted structural evidence; Task 2.8/S2C external human acceptance remains
  independently pending and continues to gate only the acceptance-oracle work that names it.
- Original PostgreSQL remains paused, original Milvus/forensic bytes remain frozen, active release/
  index pointers remain unchanged, and the S11C-owned transient database is absent after tests.
- Until S11C acceptance, Tasks 11.1-11.5 and the formal ledger remain unchanged. At acceptance, the
  only task delta is those five checkboxes together.

## TDD RED contract

Create one exact owner:

```python
def test_s11c_reconciles_all_consumer_evidence_without_legacy_dependency() -> None:
    evidence = load_s11c_acceptance_evidence()
    validate_s11c_acceptance_evidence(evidence)
```

Before candidate import, PostgreSQL connection, source read, or legacy import, it requires the S11C
overlay, failure ledger, guarded-wrapper receipt, predecessor-rerun receipt, disposable-PostgreSQL
lifecycle receipt, and only the collected-nodeid/JUnit paths declared by that ledger. Normal RED
runs the exact owner nodeid below and is exactly one strict xfail. Forced RED is exactly one
`_MissingS11CAcceptanceEvidence` failure before any effect.

```bash
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_consumer_acceptance_contract.py::test_s11c_reconciles_all_consumer_evidence_without_legacy_dependency -q
```

GREEN parses only repository evidence and predecessor receipts. It validates Accepted S11A/S11B
identity, the frozen inventory/overlay relation, exact JUnit-nodeid-signature-ledger bijection,
passing replacement owners, required Task 11.2 evidence families, and zero unresolved accepted-
behavior failure. Tampered temporary copies must fail for inventory hash, overlay coverage,
disposition, nodeid, signature, duplicate/missing ledger row, replacement outcome, and evidence-
family omissions.

## Required checks

- Historical S11A, successor S9J, and S11B contracts/receipts are Accepted and hash-consistent under
  the explicit latest-Accepted-owner-per-path authority chain before Ready.
- S11B inventory raw bytes equal the exact Accepted receipt hash and are never modified/regenerated.
- Focused normal RED is exactly `1 xfailed`; forced RED is one exact missing-evidence sentinel before
  effects; focused GREEN is exactly `1 passed` with no skip/xfail/XPASS.
- Overlay `(category, path/module)` set equals the exact frozen `s11c_disposition` key set and has
  zero unresolved entries. Retired rows bind either an already-final matching frozen base entry or,
  only for a base `s11c_disposition`, its exact overlay entry.
- JUnit failures/errors and ledger rows are bijective by run/nodeid/outcome/signature; every retired
  row has a matching inventory/overlay entry and passing owner; no accepted-behavior failure exists.
- The ledger raw-hash-binds the guarded-wrapper receipt; each run's signature root is the receipt's
  effective run root cross-checked against a terminal owned child receipt, never inferred from argv.
- The guarded receipt proves `real_subprocess`, exact Accepted S11B producer/owner authority,
  post-process terminal capture, cleanup, Admin selection, and exactly two guarded runs; any extra
  targeted ledger run is pass-only.
- The validator consumes the exact predecessor v2, preserved-v1 binding, guarded-execution
  provenance, and disposable-target receipts and cross-binds their command/cwd/UTC/source-hash/
  nodeid/JUnit/cleanup authorities to the ledger.
- S2C Task 2.7 structural tests, public interface/scenario/trace replay, disposable PostgreSQL, and
  release/index adapter owner families pass with exact recorded identities/hashes.
- Final S11A/S11B owner commands pass unchanged with exact rerun receipts; applicable nodeids are
  independently cross-bound to passing broad JUnit.
- The guarded wrapper produces only Admin and Canonical V2 predecessor ledger inputs. A separate
  postflight receipt proves the immutable predecessor artifacts plus the post-ledger focused S11C
  result form the exact complete Canonical V2 union; failures remain visible and dispositioned.
- The S11C disposable-target receipt proves nonexistence before creation, exact container/base/
  marker/backup-gate identity, Task 11.2 result, marker-owned cleanup, and final absence without
  storing credentials.
- Ruff check/format, `py_compile`, changed-scope Pyright, strict OpenSpec, `git diff --check`, scope,
  secret, generated-cache, locked-offline package-content, source parity, frozen-source, active-
  pointer, and no-online-write gates pass.
- One independent implementation/test-integrity review reports zero open Critical/Important.
  Minor/YAGNI findings are recorded and non-blocking.

## Evidence to update

- This contract and the S11C audit/implementation plan.
- S11C-local disposition overlay, failure ledger, collected-nodeid files, JUnit XML, preserved
  `predecessor-reruns-v1.json`, authoritative `predecessor-reruns-v2.json`,
  `guarded-execution-provenance-v1.json`, focused/postflight evidence, disposable-target receipt,
  review report, and `verification-receipt.json`.
- At acceptance only: OpenSpec Tasks 11.1-11.5 together and authorized acceptance/change-log/agent-
  link plus verification/portfolio/convergence pointers.
- No S9/S10/S11A/S11B/S12 or S2C artifact.

## Stop conditions

- Historical S11A, successor S9J, or S11B is not Accepted; the explicit authority-chain receipt,
  file, or inventory hash is stale; or a predecessor owner regresses.
- The Accepted inventory would need modification/re-hashing as a new authority, or an overlay cannot
  resolve every `s11c_disposition` entry with a passing exact owner.
- A JUnit result cannot map uniquely to a collected nodeid/signature, a failure is unaccounted, a
  replacement owner fails, or a changed/accepted-behavior failure would need a waiver.
- The fixed S11C disposable database already exists before this attempt, the owned container/base/
  marker/backup-gate identity is stale, cleanup ownership cannot be proven, or final absence fails.
- Task 11.2 would require prose gold, external-human S2C review, generic/original PostgreSQL, a live
  provider, or production behavior changes.
- Aggregate checks require changing production, an existing test, Accepted artifacts, inventory,
  schema/migration, source/index/pointer state, or another slice.
- Partial task closure, S12/user acceptance/Cutover, or unresolved Critical/Important enters scope.

## Done means

- Historical S11A, successor S9J, and S11B are Accepted; the Task 1 guarded-wrapper owner is GREEN;
  reviewed S11C hashes move Specified to Ready; exact acceptance-evidence RED/GREEN then exists with
  no production delta.
- Frozen inventory authority remains byte-identical; the separate overlay resolves every pending
  entry, and retired rows reconcile directly to final frozen dispositions or to the overlay under
  the exact allowed mapping, always with a passing exact owner.
- Required Task 11.2 structural/interface/trace/PostgreSQL/release-index evidence passes without
  S2C external human review or prose gold.
- Broad JUnit has complete exact nodeid/signature/disposition accounting and zero unaccounted or
  accepted-behavior failure.
- Independent review is `C0/I0`; Tasks 11.1-11.5 close atomically with exact ledger delta `+5` and
  no S12/Cutover/user-acceptance claim.

## Rollback note

Before acceptance, remove only the new S11C test and S11C-local evidence, and remove the transient
database only when its S11C receipt proves this attempt created it and its marker still matches.
If accepted evidence is
later invalidated, restore S11C status/evidence and uncheck Tasks 11.1-11.5 together. Accepted S11A/
S11B, the frozen inventory, production, databases, indexes, sources, providers, release pointers,
remote Git, and Cutover state require no rollback.
