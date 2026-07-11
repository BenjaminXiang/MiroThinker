# S4 Immutable Evidence Landing Review

## Disposition

- Status: **Accepted**
- Accepted at: `2026-07-11T22:07:12Z`
- Authority: user-authorized objective-verification self-approval
- Scope: OpenSpec tasks 4.1-4.5, landing interfaces/adapters/PostgreSQL storage and migrations,
  bounded real-source tooling, checkpoint/restore tooling, tests, and evidence
- Reviewed Task 4.4 commit: `cef42a1e075d30c5a0e179f34ab543b4878edabd`
- Independent read-only final reviews: two `Ready` verdicts
- Open findings: zero Critical, zero Important

S4 is safe for S5 to depend on as immutable landing evidence. This acceptance does not accept a
canonical identity, assertion, domain projection, release, index, query, answer, or production-like
target.

## Review findings and resolution

| Finding class | Acceptance risk | Resolution and evidence |
|---|---|---|
| Destination identity and stale environment | A replay or migration could reach the wrong database | S4D now binds the exact candidate container, database, marker, system ID, PGDATA volume, network, ports, restart policy, C2_0004 revision, and bounded pre/post state; generic URLs are never used. |
| Source/output aliasing and mutable evidence | Original, backup, restore, or committed evidence bytes could be overwritten or confused | Original/backup/restore members are rehashed with stable descriptors, require pairwise distinct inodes, and are revalidated around replay and checkpoint boundaries. Outputs are exclusive and outside protected roots. |
| Frozen summary versus live target evidence | Adding current target fields would invalidate the accepted byte-stable summary | The fresh summary stays byte-identical at `a88b44fa...e80b5`; a separate execution receipt binds target before/after, gate, tool/matrix/OpenSpec/worktree identities, run/time, and zero provider calls. |
| Incomplete logical checkpoint | Empty/missing tables or a false-zero integrity query could pass | S4E binds the exact 26-table C2_0004 inventory, every table row count/content hash, normalized schema fingerprint, exact integrity-key set, and corrected `finished_at` plus outer-count partial/error query. A real read-only candidate probe executed the SQL. |
| Unsafe disposable restore lifecycle | A name collision, transient init server, wrong image, network/storage drift, or name-based cleanup could affect another container | Name absence is required before creation; Docker's returned 64-character ID owns every later action. Final readiness requires PID 1 `postgres` plus three stable probes. Image, network-none, no ports, read-only rootfs, tmpfs PGDATA, bounded socket, marker, and distinct system ID are verified. Cleanup gracefully stops and removes only the owned ID, then proves container/socket absence and Docker-volume parity. |
| Unfrozen policy or dirty implementation | A changed threshold, corpus, OpenSpec tree, or untracked tool could silently become checkpoint policy | Exact accepted threshold/corpus hashes are constants. The manifest binds full Task 4.4 commit, Git status/diff hashes, OpenSpec tree, and explicit S4D/S4E tool/test byte hashes; fresh execution identities must equal those current values. |
| Response-family wording | The real matrix has a degraded recorded response, while live recollection is forbidden in S4E | Two-part closure is accepted: Task 4.2 proves a complete `newly_collected_response` envelope through the public adapter; Task 4.4 proves real degraded `recorded_collected_response` bytes preserve known URL/body and type missing HTTP provenance. This covers complete and degraded recollection inputs without a live provider call or invented metadata. |

## Evidence Landing acceptance mapping

1. **Artifact chain of custody — passed.** Fifteen registered artifacts retain source kind/locator,
   content SHA-256, size, acquisition time, run ID, and nine validated parent edges. Six are roots;
   no parent is orphaned or hash-mismatched.
1. **Parser history and error identity — passed.** Six ingest runs and six parser runs retain parser,
   schema, options, start/finish identity, record locators/order, and typed errors. Append-only and
   new-parser coexistence are covered in memory and real PostgreSQL.
1. **Representative matrix — passed.** The bounded matrix covers WAL/FPI partial rows, SQLite,
   JSONL, XLSX, Milvus verified-copy records, and the accepted two-part response family above.
1. **Partial evidence without invention — passed.** Seventeen records are parsed and four partial;
   three `missing_external_content` and three `schema_mismatch` errors preserve readable fields.
   Integrity probes report zero placeholders, orphan lineage, cycles, incomplete identities, or
   partial records without errors.
1. **Replay/checkpoint parity — passed.** Fresh guarded replay is byte-identical to the committed
   summary. Source and independently restored databases share logical SHA-256
   `6328e811d9c63f519c47f4dd7fe1a662e34b71ca6afb266688a5171d063054e8` over the
   exact 26 tables, while source/restore PostgreSQL system identifiers are distinct.

## Checkpoint and restore evidence

- Checkpoint ID: `canonical-v2-s4-landing-20260711T215953Z-cef42a1`
- External frozen root:
  `/md1/mirothinker-backups/canonical-v2-s4-landing-20260711T215953Z-cef42a1`
- Candidate manifest SHA-256:
  `ab091aac1cfbf2ba1699f521b9a5629d4d9b02dfb236e0600a4f711219c966b1`
- Restore verification SHA-256:
  `caf789ae87dc4c0429e068dcc3421c8d1346bec02296f6d056d816a3416f0acc`
- Freeze receipt SHA-256:
  `1c7f9b7e130835e8c70e36b90209a7a36d756971ea1ccf748a09398553e2b852`
- Frozen tree SHA-256:
  `4ae5f2ce64e4d46101a164a3c8d0a14395b6d34015338cd9fadfa09096b05012`
- Acceptance record SHA-256:
  `20e11fbe2506a44913e58351ef27121065c0b63bfa12a85cdf9425db6578f58c`
- Source system ID: `7661313446684311592`
- Disposable restore system ID: `7661394091808735279`
- Revision/schema/logical parity: C2_0004 / exact / exact
- Non-landing business rows: zero before dump, after dump, after restore drill
- Restore cleanup: owned container absent, socket root absent, Docker volume set unchanged
- Freeze: root `0550`, files `0440`, no writable checkpoint path

## Verification results

- Focused S4D/S4E: `48 passed`
- Default Canonical V2: `73 passed, 33 explicit skips, 4 expected xfails`
- Real isolated disposable baseline/integrity/landing: `35 passed`
- S1 target safety and generic-fallback coverage: `10 passed, 5 explicit skips`
- S2/S2B: `32 passed`
- Ruff: passed
- Pyright: zero errors/warnings/information
- Strict OpenSpec, JSON parsing, Markdown formatting, and `git diff --check`: required in the final
  Task 4.5 verification pass and recorded in `verification.md`

## Pattern-fix report

- Reported case fixed: unsafe/stale target evidence around the Task 4.4 replay and Task 4.5 restore
  checkpoint.
- Defect class: destination admission, source/evidence aliasing, lifecycle ownership, and evidence
  binding were individually plausible but not yet one atomic fail-closed contract.
- Sibling patterns searched: replay outputs, all source families, Docker name/ID cleanup, final
  Postgres readiness, socket permissions, image/network/port/storage policy, table/integrity hashes,
  Git/OpenSpec/corpus/threshold identity, and secret-bearing command evidence.
- Sibling issues fixed: stable source descriptors and inode separation; separate immutable summary
  and execution receipt; exact inventory/integrity SQL; owned-ID graceful cleanup; final-server
  readiness; approved policy hashes; current untracked implementation binding; DSN redaction.
- Not fixed: S5+ assertion/identity/fusion/domain/release/query behavior is outside S4.
- New invariant: every real destination operation is authorized by one observed frozen execution
  context before and after, and every temporary destructive target is removed only through its
  returned owned identity.
- Remaining systemic risk: later slices must keep S4 immutable and create a new checkpoint/release
  rather than rewriting this evidence or its accepted overlay.

## Explicit non-claims

- No live Web, LLM, embedding, reranker, or Milvus provider call occurred.
- No canonical assertion, identity, decision, domain projection, release, publication, or index row
  was created.
- Original `pgtest` stayed paused; original Milvus was never opened by a client.
- No production-like promotion, cutover, source cleanup, or Task 5.1 implementation occurred.
