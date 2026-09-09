# S12A Complete Isolated Candidate Builder Dependency Audit — 2026-07-20

## Outcome

S12A and exactly Task `12.1` are Accepted after the fresh isolated r12 build, complete system checks,
two final source/safety reviews, and an independent envelope/PostgreSQL/physical-index audit on
`2026-07-23`. Streamed/indexed identity resolution and the immutable DomainProjection assertion-ID
cache preserve output, errors, ordering, hashes, schema, and API; their combined owner matrix reports
`87 passed`. The focused builder/runner matrix reports `104 passed`; the exact Task 12.1 owner matrix
reports `169 passed, 2 skipped`; complete no-external Canonical V2 reports `542 passed, 148 skipped,
3 warnings`. Ruff and Pyright pass on the complete Canonical V2 surface. S10O and aggregate S11C
remain Accepted. The formal ledger is `71/80` (80 total, 71 complete, 9 open) and remains `49/97`
acceptance checks because this build-only slice does not close an aggregate acceptance item.

The current evidence is release `candidate-s12a-20260723-r12`, run
`s12a-build-20260723-r12`, raw envelope SHA-256
`a2684f9b9bd42c8727625fa7e057f654c6539a6e97924eccfdfb913fdfef9cbc`, and canonical
envelope/receipt/handoff hashes
`77cde16c037aec888e07a677b3f96effd27a75f3eeb68a4f38c5fdb2a6a88383`,
`5ae974b6af80980864bac751812b12fb7c468a4449331db4a85b47c4453437a8`, and
`f18af1854a92ef2d76816a8f3f3a9a724fb5ab233de6020f9c161c5100cf00bc`.
Independent readers found 5,561 landing records, 1,037 Company projections, zero other public-domain
or relationship projections, 5,561 one-to-one evidence-bound gaps, 1,037 index points/documents,
zero physical parity deviations, and no active release before or after. The durable registry and
physical snapshot hashes are `5092f40fb0759dd69a297fa505b8cb50ab09fbac39d7209e602c69cffea3732f`
and `20cc5fd309056f714e09038465d3cec805e239752f1b709e0e92ba269f46cabe`.

S2C/Task `2.8` is not a S12A dependency. It gates the claim-level query/answer acceptance runs and
therefore S12B Tasks `12.2` and `12.3`, not deterministic construction of an isolated candidate.
S12A may run the strict/static checks that contribute to Task `12.4`, but it must not check `12.4`.
Task `12.5` requires later explicit user acceptance of the complete multi-gate isolated candidate,
and Task `12.6` remains a separately authorized production-like Cutover/archive/destructive-cleanup
boundary. The broad instruction to finish open work authorizes local S12A acceptance; it does not
fabricate the external human/provider evidence required by the remaining tasks.

## Remaining-task hard gates at the S12A checkpoint

- Open tasks are exactly `2.8`, `8.1`, `8.8`, `9.8`, and `12.2`-`12.6`.
- Task `2.8` still has 29 `pending_user_review` contracts, 23 explicit exclusion decisions or missing-
  evidence replacements, zero human-reviewed/acceptance-eligible cases, and 18 uncalibrated families.
  Each relevant family requires at least 50 double-reviewed samples, agreement `>=0.80`, and two
  distinct attributable human reviewers, plus authorization of a real recorded judge.
- The accepted population contract still records `all_required_samples_materialized=false`: current
  cases are Company 30, Professor 12, Patent 11, and Paper 7, below the per-domain/path, relationship,
  multi-turn, and judge-calibration populations required for Tasks `8.1`, `8.8`, and `9.8`.
- r12 honestly contains only Company projections. It therefore cannot pass the required Paper,
  Patent, Professor, relationship, query/answer/Web, latency, or cost gates. Approved targeted
  recollection is currently empty, and no named real-provider credentials are present.
- Task `12.2` still lacks its content-addressed serving bundle and production `--serve` remains
  fail-closed. Task `12.3` has valid S12A source/gap/release/index inputs but lacks the upstream
  benchmark/latency/cost/rollback aggregate. Task `12.4` must be rerun after those final artifacts;
  Task `12.5` and `12.6` retain their separate user-acceptance and Cutover-authority gates.

## Accepted foundations already available

- S2/S2B: exact backup-manifest authority over 50 sources — 48 `inventory:*` records plus
  `original_postgresql_volume` and `forensic_recovery_tree` — with backup/restore coverage and the
  executable accepted rebuild write gate. Original PostgreSQL, Milvus, and forensic sources remain
  frozen. The 48-source inventory is bound evidence but is not the complete source-ID authority.
- S3-S6R: explicit-target Canonical V2 schema, immutable landing, retained assertions/decisions,
  reversible identity, typed four-domain projections, internal Person/Technology auxiliaries,
  relationships, eligibility, and typed gaps.
- S7: `KnowledgeBuild.build(BuildCandidateRequest) -> CandidateRelease`, deterministic candidate and
  index projection builders, isolated full lookup/Milvus materialization, complete physical audit,
  exact `ReleasePublication.verify`, and immutable manifest/receipt contracts.
- S8/S9 implementation mechanics: release-bound read and grounded answer modules. Their aggregate
  claim-level acceptance remains correctly outside S12A.
- S10A-S10D: typed gap signals and offline remediation mechanics. S10O will supply the durable gap
  adapter required before S12A becomes Ready.

## Resolved hard dependencies

- **Accepted S10O:** supplies the durable typed gap destination so an unreadable, unsupported, or
  intentionally omitted evidence input becomes an inspectable gap rather than a fabricated fact or
  an untracked log line.
- **Accepted S11C:** the consumer graph, sanctioned evidence writer, V2-only imports, and legacy
  quarantine passed aggregate acceptance at `2026-07-21T19:10:41Z`; Tasks `11.1`-`11.5` moved the
  ledger from `65/80` to `70/80`.

These dependencies may now be consumed by a later Ready S12A implementation. Their Accepted bytes
must not be edited or reinterpreted by this repair.

## Historical implementation gap, now resolved for the Candidate

1. `knowledge_build.py` is intentionally pure and ephemeral. Its private materializer callback
   receives already-produced sections; it does not verify source coverage, copy bytes, ingest
   landing records, construct authority, persist a release, build a physical index, or verify it.
2. Candidate, relationship, path-eligibility, lookup/vector, physical-audit, and release-verification
   mechanics exist, but no one module owns their ordering and cross-release invariants.
3. No versioned source-build manifest accounts for all 50 Accepted S2B backup-manifest sources while
   enforcing the exact `requirements_only=7`, `acceptance_only=7`, `evidence_input=1`,
   `protection_only=5`, `registered_unprojected=30`, `unrecoverable=0` disposition. Blindly
   ingesting inventory, protected, legacy, or forensic entries would incorrectly turn non-factual
   material into canonical evidence or open protected bytes.
4. No explicit-target builder binds one fresh disposable PostgreSQL database, one fresh marked
   isolated index root, the accepted backup gate, the source-build manifest, recorded decision/
   embedding adapters, and one content-addressed final envelope.
5. No success handoff originally bound the built candidate to the five exact S11 consumer artifacts.
   The Candidate now has that handoff. Production serving and live query/answer/Web gates remain
   deliberately deferred to Task `12.2`.

### GREEN performance prerequisites found on 2026-07-22

- Reproduction: the full 5,561-row build under `pytest --no-cov` consistently remained CPU-bound
  in exact downstream owner replay; it was stopped after `9m52s` at about `1.7 GB`.
- Root cause: `domain_projection.py:509` and `:584` allocate `set(self.assertions)` once per
  decision/inclusion even though `self.assertions` is immutable for the validation call.
- Proven progress before the first stop included exact landing, domain/internal/candidate
  composition, path eligibility, pure index, candidate registry, typed stores, and embedding. The
  early run incorrectly treated 580 relationship source rows as projectable; the hardened policy
  now retains all 580 as evidence-bound `cross_domain` gaps because Accepted endpoint authority is
  absent, producing zero relationship projections.
- Resolution: the explicitly authorized identity-resolution and DomainProjection optimizations and
  their parity/large-graph regressions are implemented. Current production SHA-256 values are
  `51b5190ff0e7382b79c7a0a2e4c51d5e78680e8e5f5a42a4361b6acc37b53807` and
  `9e32141307b24b0e5fa31b4cbb7363042f3a22f5fa3e355f18cbbb7a93867cc1`; their owner matrix reports
  `87 passed`.

## Selected module and seam

Create `knowledge_build_isolated.py` as the deep implementation of the existing external interface:

```python
class KnowledgeBuild:
    def build(self, request: BuildCandidateRequest) -> CandidateRelease: ...
```

Callers and acceptance tests cross only this interface. A package-internal composition factory may
accept explicit target configuration and real adapters, but it must return `KnowledgeBuild`. Source
copy, landing, authority construction, gap recording, projection, durable registration, full index
materialization, physical audit, release verification, and envelope emission remain implementation
details. Deleting this module would force all of those invariants back into every runner/caller, so
the module provides real depth rather than pass-through indirection.

The implementation may use internal seams only where two real adapters exist:

- local-substitutable PostgreSQL/filesystem/Milvus Lite run against fresh real local targets;
- recorded and production offline decision/embedding adapters use injected ports;
- clock and single-envelope sinks have deterministic test adapters and file adapters.

The runner is deliberately shallow in capability, not in orchestration: it parses required explicit
arguments, creates the approved production adapters, calls `build` exactly once, reads the
sink-owned success envelope, and prints the returned candidate identities. The success
handoff exact-types and cross-binds `CandidateRelease`, `IsolatedReleaseBundle`,
`IndexProjectionRequest`, `InstitutionCatalog`, and `ReleaseVerification`; it is emitted only after
single-envelope readback and is not a second public build API. The runner must not call landing, identity,
build projection, index, verification, promotion, or SQL helpers directly.

The injected `--serve --host 0.0.0.0 --port 18188` test seam proves the exact handoff can be wired
to an app object without a second build, promotion, pointer change, import string, child worker, or
startup rebuild. Production dependency resolution intentionally rejects `--serve` before builder
construction. Task `12.2` owns the content-addressed recorded proposal/answer/Web/sufficiency/
supplemental serving bundle and its real query/answer gates; Task `12.1` does not claim them.

## Source-build manifest contract

The Accepted source authority is the exact 50-record `sources` list in
`s2b/backup-manifest.json`, not the 48-record S2 inventory alone. The versioned manifest binds:

- source inventory SHA-256
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`;
- backup manifest SHA-256
  `a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8`;
- restore verification SHA-256
  `98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231`;
- acceptance record SHA-256
  `3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b`.

The exact frozen disposition count is:

| Disposition | Count | Effect |
| --- | ---: | --- |
| `requirements_only` | 7 | Bound requirement authority; never landing/factual assertion input. |
| `acceptance_only` | 7 | Bound acceptance/evaluation authority; never landing/factual assertion input. |
| `evidence_input` | 1 | The sole admitted verified restore member. |
| `protection_only` | 5 | Identity/hash protection gate only; S12A never opens the bytes. |
| `registered_unprojected` | 30 | Registered with limitation; no landing/assertion/projection in S12A. |
| `unrecoverable` | 0 | No Accepted S2B source is missing or corrupt. |

The exact source mapping is:

| Disposition | Exact source ID | S2B kind |
| --- | --- | --- |
| `requirements_only` | `inventory:bfd2f9771e12452101507f8e0d10b2243f7f1807e96905ed35c327c430f349b6` | `authoritative_prd` |
| `requirements_only` | `inventory:c037008730833b28b5e9fb200a4ed9078d8571382b1250d36795d6ca18456e6b` | `authoritative_prd` |
| `requirements_only` | `inventory:5b17380f2b046730ccda68910ee8dec2af10319093d7b86734780f6a19f4c847` | `authoritative_prd` |
| `requirements_only` | `inventory:531d3cb88f7c5605d5c3fe2d8c4e6564106c71cf3d278f23b3eea6daad08d145` | `authoritative_prd` |
| `requirements_only` | `inventory:5b0c06ada31be18bfb8ce8704c3e1a7cf04346f243756b451e5d37b414328d2f` | `authoritative_prd` |
| `requirements_only` | `inventory:619924e69182f9fffe9bef24455d50ebee787fabe9fb92b74e413a5e7a46544c` | `authoritative_prd` |
| `requirements_only` | `inventory:7bbd1e8e41e98162add1fbb385443061ac91b8a8fd7e0da3fa9a2a6a5dac47ee` | `authoritative_prd` |
| `acceptance_only` | `inventory:e425f399185195b5e1c187db87869032e000e9c7e17b29353b61bce1b6ce025f` | `seed_scenario_workbook` |
| `acceptance_only` | `inventory:9d70d6f276e39cd177079766739fbce58723ef79435cf502eedd798207f5c720` | `committed_eval_fixture` |
| `acceptance_only` | `inventory:43c44a4cb584803b79fcd4760461af7dcd68304ac163d961a83643067e5227d8` | `committed_eval_fixture` |
| `acceptance_only` | `inventory:03cdece09485247f5a036871021e770a9b3b35c25a515fb0314655589f5d9c44` | `committed_eval_fixture` |
| `acceptance_only` | `inventory:c72421b11813abe836836545eb8925076e5e3c09b975a9a11387b7fef6e8bde4` | `committed_eval_fixture` |
| `acceptance_only` | `inventory:55c969432f588015934396a66874ea6b533d431aa3b521a61f5681c4f2f886a2` | `committed_eval_fixture` |
| `acceptance_only` | `inventory:d26dd2f6d1e9a24699d642b68760c03df65b13e07edc5335868d5923eab43189` | `committed_eval_artifact` |
| `evidence_input` | `inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0` | `sqlite_snapshot` |
| `protection_only` | `inventory:65c4a289550957659155a00799158dd615be14005eb8f35afc778cfa3943accd` | `milvus_lite_original` |
| `protection_only` | `inventory:5880891dd3b3c04f1f8e9b29c308dd9be12b233a3165338bf992c17f3aa848a8` | `legacy_milvus_hash_only` |
| `protection_only` | `inventory:1a873f91cf59065877e3b21a5b5a046c3c7705b128d9ae8c9db31c23588e439f` | `host_ext4_journal_copy` |
| `protection_only` | `original_postgresql_volume` | `original_postgresql_volume` |
| `protection_only` | `forensic_recovery_tree` | `forensic_recovery_tree` |
| `registered_unprojected` | `inventory:f8fea06321bd45af4c88c9654497a8c504defbf56c5eaee1d758e26248ea2bae` | `committed_backfill_jsonl` |
| `registered_unprojected` | `inventory:4384044cb138f62be89edc0f9457065d00f08ce44d8dd9d06e0caefc555c3eef` | `committed_backfill_jsonl` |
| `registered_unprojected` | `inventory:82e601426705c3ab7ea24b9b9736975fc8f22128e077aa279075e19558309ee3` | `committed_backfill_jsonl` |
| `registered_unprojected` | `inventory:8c3084c6d7364e43089903d8bd60c182534aa199eb7c04e6721291ad0b358e99` | `committed_backfill_jsonl` |
| `registered_unprojected` | `inventory:1a987406c94c0f1e7b69e0272d8f06582f7f1fe2668f3cfbdd0e48780eed3026` | `committed_backfill_jsonl` |
| `registered_unprojected` | `inventory:98a87f5fea987e586f33ead0914b848d4acd9e03a3312eaa5a8eb01f7c8765f5` | `committed_backfill_jsonl` |
| `registered_unprojected` | `inventory:b84a6eac6bc59c9b9431b94ae8735bcda813b3186c28455719ac3bd6718d41ae` | `committed_backfill_workbook` |
| `registered_unprojected` | `inventory:b9a8975b2d147348ef47cbd08ad12c6e550c6012ecc29e2979a4db76e3b3c4a0` | `committed_backfill_workbook` |
| `registered_unprojected` | `inventory:306888219094fdee6713d1d21bf2716d8fd1326efaf5a7a4875c08ce3cbc58f5` | `company_source_workbook` |
| `registered_unprojected` | `inventory:5eed796459843f74ecaebf4f0f8b20fd4570d2a343a442f9ddcbe0f26362d6ab` | `patent_source_workbook` |
| `registered_unprojected` | `inventory:6cf786f09478810a09cffe194d96e046a4d3e28a465c4418d8be2a13a126e5f7` | `professor_merged_jsonl` |
| `registered_unprojected` | `inventory:27e2129243e993646d1e976814f26fd42590dd6c02639577c1ce6cdf36329ce7` | `legacy_professor_jsonl` |
| `registered_unprojected` | `inventory:3bf673d8c10db3fc95558037794443a0b8f4a3994d5ae36ac7c85191440f1cd6` | `professor_fetch_cache_family` |
| `registered_unprojected` | `inventory:2d237edecb0f22c141c270f0c9147e3c5a18824025d155f607bb58ef79acc1bb` | `paper_openalex_cache_family` |
| `registered_unprojected` | `inventory:603b9b33d7e8f3581d670659002768778ec06914a1f1586a0742619024038083` | `paper_orcid_cache_family` |
| `registered_unprojected` | `inventory:b2fd4e9bcf4238424785571f65e94161f07f9631a5b589ace749397527ac35ad` | `legacy_release_jsonl_family` |
| `registered_unprojected` | `inventory:3371136d61fe041eb7e7ba087d9ddc37843330b4d39187b355310ba50599d1d2` | `legacy_sqlite_snapshot_family` |
| `registered_unprojected` | `inventory:7a323115d06360192111c84e2a4da324146948d18c3189751885f6b95ac6d255` | `legacy_data_agent_jsonl_family` |
| `registered_unprojected` | `inventory:aa84883ccf6e8034b9ebe6d03fa91d6b265f4abd1f096ceb13d219d38a1a6435` | `admin_upload_workbook_family` |
| `registered_unprojected` | `inventory:dc465266f3a71f9c820cba8cf83f860feb053f6da5bfef79ec02283e9f5ee673` | `admin_upload_jsonl_family` |
| `registered_unprojected` | `inventory:c2199ac16504af74d0e8a0a00c7e9fea5cf79c65c9de9631ceaa81a3ad0347d2` | `compressed_backup_family` |
| `registered_unprojected` | `inventory:6533126e9f7b14a478e8fc098541258d9b075ce70de16288b43dcf9abed59cc1` | `raw_pdf_family` |
| `registered_unprojected` | `inventory:573305265d755bf3d85fb60e5e3d33e588838f7d71075d663f5f1b6836bf3ff7` | `historical_milvus_file_family` |
| `registered_unprojected` | `inventory:11c9847d8bb362984a35e54c25d6f3f01f74b6209245d359e40f7dbd98738829` | `forensic_checkpoint_document` |
| `registered_unprojected` | `inventory:eb4faa13a8f4c00f703b2fb014ecc5eb671cb29b3dd20e0836afb9b1024bf8a0` | `recovery_experiment_document` |
| `registered_unprojected` | `inventory:d0306b9ab385b64379e437978a971e1d4a8abecee0de0863e0cdb53163b1028d` | `recovery_plan_document` |
| `registered_unprojected` | `inventory:20be9e411f58e2d8a13f82ff094c5424074ba95bf6668177f64edc2396463d07` | `ext4_directory_inode_copy` |
| `registered_unprojected` | `inventory:5e1ba9daab456914060f8df8b826a57006cb6ae8486ac816f7b1721186c17c73` | `postgres_salvage_dump` |
| `registered_unprojected` | `inventory:909ada3e637a0220acc7d7a6335d3743045762e5c720e6120141c79ae5b0d8f8` | `recovered_paper_id_manifest` |
| `registered_unprojected` | `inventory:bdb272f5232f7d7bdb9df3e6341f8be4235c57bcc7f11917cb628b216a7367b5` | `recovered_link_id_manifest` |

The sole `evidence_input` binds restore member
`workspace/logs/data_agents/released_objects.db`, exact size `20267008`, SHA-256
`7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce`, backup member-manifest
path `manifests/inventory/027-ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0.jsonl`,
backup member-manifest SHA-256
`6820786a2e055def2828c82de60f3b90cad9ac5dcc8f1477943a9f46a02777ae`, and source-member-manifest
SHA-256 `4c91d1d7dce88e5c9d9924b2c21d6f3111292eb3e5c30a60e688fd40ccf8b594`.

The S12A batch is a new full-table batch, not S4D's `limit=5` batch or the P1 five-row preview. It
requires exactly 5,561 `released_objects` rows with exact type counts `company=1037`, `paper=574`,
`patent=1931`, `professor=1439`, and `professor_paper_link=580`. These are source-row counts, not
projection targets. The accepted mapper produced 1,037 Company projections; all other source rows,
including the 580 relationship rows, produced typed evidence-bound gaps because the available
payload did not satisfy the accepted field/endpoint authority. An S12A-private reader uses the
Accepted schema-introspection rules on the candidate-owned verified copy, requires one stable
single-column primary key, quotes the introspected identifiers, and executes deterministic
primary-key `ORDER BY` with no `LIMIT`. It neither assumes an `id` column nor uses/modifies the
Accepted `HistoricalSqliteAdapter` unordered no-limit path. Schema/primary-key/count/type drift
fails before landing or projection as applicable.

The manifest also freezes a content-addressed released-objects mapper policy. Rows remain historical
assertions, not canonical truth; allowlisted fields flow only through Accepted decision, identity,
domain, relationship, eligibility, and index owners. A relationship requires explicit policy-listed
typed endpoint IDs that both resolve in the same release. Product capability remains answer-scoped;
no Product projection or placeholder identity/parent/fact/relation/evidence/point is allowed.
Malformed, unallowlisted, unresolved, cross-release, or unmapped row/field content retains readable
evidence where safe and creates a typed S10O gap with exact row/field/path reason.

Separately, targeted recollection may contain immutable staging members only when each entry has an
explicit approval reference. The current set is empty and the builder never launches recollection.
Missing/extra/duplicate 50-source authority, disposition-count/mapping drift, duplicate IDs,
tampered member lineage, ambiguous roots, original/protected/symlink/hard-link input, or request/
manifest batch/version disagreement fails before landing. Only `evidence_input` may enter landing.

## Complete build sequence

`KnowledgeBuild.build` owns and records this finite sequence:

```text
accepted S2B gate + exact request/manifest/target preflight
  -> candidate-owned verified copies (hash/size/lineage checked)
  -> immutable PostgreSQL EvidenceLanding ingest/stream
  -> retained assertions/decisions/identity + typed gap drafts
  -> four public domain + Person/Technology + relationship + eligibility projections
  -> pure full-index expectation + immutable BuildManifest/CandidateRelease
  -> durable candidate/release/manifest + available typed stores + unresolved gaps
  -> fresh marked isolated lookup/Milvus full build and complete physical audit
  -> exact ephemeral ReleasePublication.verify only (never promote)
  -> one canonical-JSON content-addressed receipt/handoff envelope readback
```

The implementation replays every caller-independent stage result through its Accepted owner before
trusting it. All release IDs, build run IDs, source batches, as-of values, policy/parser/model
versions, public/internal scope discriminators, relationship authority, eligibility decisions,
projection hashes, point/document inventories, database registry rows, index metadata, and envelope
hashes must agree.

The durable registry uses the live existing schema; S12A adds no migration. After the pure graph and
expected index manifest are known, it atomically inserts the release/build-manifest/manifest-section
identity, persists identity/decision/domain/relationship rows through their Accepted stores, then
records typed gap drafts against that durable candidate. No Accepted store exists for internal-
reference or path-eligibility results; their hashes remain in manifest sections and their exact typed
payloads remain in the single success envelope/handoff. A later failure may leave an isolated candidate marked
inspectable/retryable, but `build` does not return success, no active pointer changes, and no partial
candidate becomes serviceable. Store-level replay inside one build is idempotent; conflicting
content identity fails. A retry uses a new run/release identity and complete fresh target set rather
than deleting or overwriting an old target.

## Failure and gap behavior

- Hash/lineage/target/gate/cross-release failures stop before the next effect and produce no
  successful envelope.
- Parser partial/quarantine outcomes retain readable evidence and typed source errors. Missing data
  never creates placeholder identities, assertions, parents, relationships, or projection points.
- An accepted `unrecoverable` disposition or downstream evidence insufficiency records a durable
  S10O gap bound to source/release/run/domain/path evidence. The gap does not close during S12A.
- Recorded decision-adapter failure leaves the candidate unpublished and retryable. Model memory is
  never source evidence.
- Physical index drift or a non-accepted `ReleaseVerification` prevents success even if an envelope
  or aggregate manifest appears plausible.

## Target and publication safety

- PostgreSQL must be a newly created, explicitly named and marked `disposable` target at the live
  single migration head; generic `DATABASE_URL`/`DATABASE_URL_TEST` fallback is forbidden.
- The index root must be absolute, newly marked for the same candidate release, physically fresh,
  non-symlink, non-network, and different from the original/retained accepted index targets.
- Candidate staging has a machine-validated marker containing exactly its marker schema/version,
  `run_id`, `candidate_release_id`, and `source_manifest_sha256`; every candidate-owned copy stays
  beneath that root. A later cleanup may touch it only after the same exact marker and ownership
  fields validate. A failed durable target is retained rather than overwritten or silently removed.
- Production code may copy only the manifest-bound Accepted restore member under the Accepted
  restore root. It resolves the backup member-manifest path beneath the backup root, checks its
  path/size/hash record, opens the restore member with `O_NOFOLLOW`, verifies stable `fstat` identity
  around streaming/hash/copy, and proves restore/staging inode independence. It must not import
  `.agents` S2B/S4D helpers: the S4D verifier also opens original source paths and is forbidden in
  the S12A production path.
- The accepted backup gate is checked before source read, before the first database write, and
  immediately before the first physical index write.
- S12A first calls `audit_isolated_index_snapshot` to enumerate the actual complete physical index,
  then uses the package-private Accepted `create_ephemeral_release_publication(...).verify` for exact
  S7F reconciliation. The publication object is never exposed. The isolated publication wrapper,
  which requires prior/candidate bundle registries and one active release, is not used on this fresh
  absent-active target. S12A never calls/exposes `promote`/`rollback`, changes
  `publish.active_release`, moves an alias/pointer, or discovers a latest release. An independent
  database read proves `publish.active_release` absent before and after.
- Original `pgtest`, original Milvus, backup bytes, restore evidence, and forensic sources remain
  unchanged. S12A checks only the Accepted original-Milvus identity record; it never opens or
  rehashes the original bytes.

## Alternatives rejected

### Put orchestration in `complete_candidate_runner.py`

Rejected. It would be a thin `KnowledgeBuild` wrapper while forcing every caller/test to understand
stage order, target safety, replay, and failure semantics.

### Add a new S12 persistence schema

Rejected. Existing landing/knowledge/domain/publish/ops schemas already own the required records.
S12A needs composition and exact replay, not another event store or migration.

### Close Task 12.3 from the build receipt

Rejected. The receipt can contribute release/index/source evidence, but Task `12.3` explicitly also
requires aggregate recovery coverage, unresolved gaps, rollback, and benchmark evidence. The
benchmark portion depends on accepted S2C/S8.8/S9.8 results and belongs to S12B.

### Combine candidate construction, user acceptance, and Cutover

Rejected. Task `12.5` is a user decision and Task `12.6` requires separate authorization. Neither is
an implementation shortcut.

## Exact task boundary

After a successful real isolated run, all Required checks, and independent acceptance, S12A may
check exactly Task `12.1`. It must not check Tasks `12.2`-`12.6`, Task `2.8`, `8.1`, `8.8`, or
`9.8`. Compute the live ledger at acceptance; the S12A delta is exactly one checked task.

## Readiness review disposition

- Critical found and repaired: `3`.
  1. Source authority now comes from all 50 Accepted S2B backup-manifest `sources`, not the
     incomplete 48-record inventory alone.
  2. The sole evidence input now has an exact full 5,561-row extraction and versioned historical-
     assertion mapper; S4D/P1 bounded previews cannot masquerade as complete source authority.
  3. The build receipt now includes a sink-readback consumer handoff, so the run-local app consumes
     the exact private-stage outputs without reconstructing them.
- Important found and repaired: `4`.
  1. The exact `7/7/1/5/30/0` disposition and 50-source mapping are frozen above.
  2. Historical rows pass through explicit field/relationship allowlists and Accepted identity,
     decision, projection, and gap owners; no Product/placeholder shortcut exists.
  3. The historical plan gave the runner an injected single-build `0.0.0.0:18188` wiring contract.
     The implemented production path is narrower: it fails closed before builder construction until
     Task `12.2` supplies the content-addressed serving bundle and live gates.
  4. RED has eight import-first groups, and target/source-copy/cleanup boundaries now freeze exact
     staging markers, stable no-follow reads, independent inodes, full physical audit followed by
     ephemeral verify, and the Tasks `12.2`-`12.6` boundary.
- Open Critical/Important: `0`.
- Minor/YAGNI, nonblocking: do not add a workflow engine, resumable DAG framework, distributed
  transaction coordinator, generic source plugin registry, automatic cleanup/retirement policy, or
  real-provider run to S12A.
- At the time of this first repair, status remained `Specified`; it did not waive live-head/source-
  ownership checks or the independent lean Ready review. The later evidence below supersedes that
  historical status only after every gate passed.

### 2026-07-22 lean Ready review repair

The next independent review reported `Critical=1 / Important=6 / Minor=1 / YAGNI=0`. This revision
repairs the blocking findings without changing Task `12.1` or starting implementation:

1. S12A never opens or rehashes original Milvus bytes. Ready/final gates consume only the Accepted
   S2/S2B content-addressed identity record and the executable 50-source backup gate.
2. `SourceDisposition` covers all six exact states, including the five `protection_only` and thirty
   `registered_unprojected` entries.
3. The typed receipt binds an exact five-artifact `CompleteCandidateConsumerHandoff`; this first
   repair incorrectly described two-file atomic publication and is superseded below.
4. Ready commands now prove the unique Alembic head, S2B hashes/formal gate, paused `pgtest` metadata
   and source-volume identity, all-worktree ownership, and the Accepted original-Milvus record
   without opening protected bytes.
5. Fresh database/index/staging targets are represented by the Accepted database/index target
   models plus one exact staging marker/target model and one private fail-before-read validator.
6. Task 3 turns only the six build groups GREEN; Task 4 later turns the two runner groups GREEN.
7. The user-required local commit occurs exactly once after Task `12.1` acceptance; Push/PR remain
   forbidden.
8. Top-level `build` is single-use per fresh physical target set. Store-level replay/collision and
   envelope readback remain tested inside that build; retry requires new run/release
  identities and new fresh targets.

The mechanically checked 50-source mapping remains exact at `7/7/1/5/30/0`. The first Ready review
bound Specified SHA-256 values contract
`33252aa28fe7c765ec371e3824ad9f52295af14931b3d9b783b628d12ece666b`, audit
`4d3fd293621e527b624609e11a0285461e192fceff77849fe4e9ac749f411e72`, and plan
`39ebf4376d99a10e8f919e8ec14c6329f86a73a5051f4067aa6463d60705c24c`. Live Ready evidence:
unique `C2_0011` head; S2B `state=accepted/source_count=50`; paused original PostgreSQL on volume
`d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; no competing writer;
owner matrix `71 passed, 2 skipped`; strict OpenSpec and `git diff --check` exit `0`. These live
checks remain valid, but the status was revoked by the later storage-seam findings.

### 2026-07-22 storage-seam repair

The read-only storage audit found two Important contradictions after the first Ready review and
before any RED/implementation file was created:

1. Existing PostgreSQL adapters cover identity, decision, domain, relationship, release/manifest,
   and gap rows, but there is no Accepted store/schema for `InternalReferenceProjectionResult` or
   `PathEligibilityResult`. S12A now stores their exact hashes in manifest sections and their exact
   typed payloads in the success envelope/handoff; it adds no migration, table, or unrelated-column
   serialization.
2. Two unrelated JSON files cannot be crash-atomically published by filesystem rename. The sink now
   writes one `CompleteCandidateBuildEnvelope` containing the typed receipt and five-artifact
   handoff, fsyncs one temporary file, publishes it through a same-filesystem no-overwrite hard
   link, fsyncs the directory, and reads back the same canonical file before success.

The exact 50-source mapping, deep `KnowledgeBuild.build` interface, failure isolation, no-promotion
boundary, and earlier live gates are unchanged. The focused independent re-review accepted these
repaired bytes with zero open Critical/Important findings, so Ready was restored at
`2026-07-22T11:57:23Z`.

## Candidate execution disposition — 2026-07-23

- r1-r6 are retained historical build attempts against earlier code; r6 emitted the untracked
  historical `complete-candidate-build-envelope.json` and is not current Candidate authority.
- r7 failed before landing on SQLite WAL header handling. r8 and r9 were stopped after read-only
  review found real target/source safety blockers. Their owned resources remain retained for audit.
- r10 completed under an older implementation. r11 completed, but its review found four blocking
  source/target audit findings. Both remain retained historical evidence and are not authority.
- r12 used the final reviewed implementation, fresh isolated database
  `miroflow_candidate_s12a_20260723_r12`, fresh staging/index roots under
  `/var/tmp/mirothinker-canonical-v2-s12a/r12`, and no production resource. It completed and emitted
  the current evidence copied as `complete-candidate-build-envelope-r12.json`.
- Independent current-model envelope, read-only PostgreSQL, and byte-copy physical-index audits all
  pass. `publish.active_release` is empty; original `pgtest` is still paused; original Milvus was
  not opened or rehashed. Final source/safety/evidence reviews are GO with zero Critical/Important,
  so S12A and exactly Task `12.1` are Accepted.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{proposal,design,tasks}.md`.
- All active specs under
  `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/`.
- Accepted S2B, S7, S10O, and S11C Slice Contracts and receipts; S11C receipt SHA-256
  `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`.
- Current `knowledge_build.py`, `candidate_projection.py`, `index_projection.py`,
  `index_projection_isolated.py`, `release_publication.py`, and
  `release_publication_isolated.py` as implementation evidence.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/convergence-plan-remaining-24-2026-07-20.md`.

No production code, test, source manifest, database, index, envelope, task checkbox, status ledger,
Commit, Push, PR, promotion, archive, or Cutover changed during this audit.
