# S11C Aggregate Consumer Acceptance Dependency Audit — 2026-07-20

## Outcome

S11C is a pure acceptance slice by default. It adds no production behavior, migration, runtime,
route, UI, writer, retrieval implementation, or compatibility fallback. Its only implementation
artifact is one aggregate acceptance-contract test that binds already-Accepted S11A/S11B evidence,
the frozen S11B quarantine inventory, exact broad-test JUnit results, replacement owners, and a
separate S11C disposition overlay.

S11C is **Accepted** at `2026-07-21T19:10:41Z` after Candidate at `2026-07-21T19:05:17Z`. Its former Ready authorization at
`2026-07-21T15:02:07Z` remains superseded. The execution re-authorization at
`2026-07-21T17:42:54Z` was superseded for Candidate progression when final evidence review found
one Important traceability gap: predecessor reruns lacked exact cwd, and guarded broad runs lacked
machine-validated UTC windows. A v2 predecessor receipt and raw-hash-bound JUnit provenance
supplement now close that gap. Focused/full validators, capture owners, static checks, generated
cleanup, independent evidence review, and protected-scope review are GREEN at zero open Critical/
Important. The final receipt is `s11c/verification-receipt.json`. Tasks `11.1`-`11.5` closed
atomically and the formal ledger moved `65/80 -> 70/80` with no other task change.

The exact repair hashes are validator
`3924a00af6dbe183f0a1199ed7b9977b5475dad3ee558b4fa4fd7758f9ca62bb`, helper
`a1bbf4d60ee2e73aee93a27ff3d75a6d94526f08d4701c243c40ca204da7bdf4`, owner
`060c7ab2979bb9d69b6a30533660205d226ef5bb660cd62897616ddff171db8c`, guarded provenance
`8b307160f9f1231896d11f43d71b06daed329824a50f3255a127d922aa35f467`, preserved v1 receipt
`84507b7c3fd6a441547922cfc7012c58a74b6a11c82ec001ffe8e300ffc5eb11`, and authoritative v2 receipt
`6043e991ff2971aba8bb5a1492261be302412aab1cb272b9027ac24009282d8d`. The immutable broad ledger
and guarded receipt remain respectively
`271f4f9808a206e06cd616c95a778178f453fb67cf9284e9b93c33623fb75e7d` and
`9b5e1c786bc62e6df5b7736e3fd9f1bf47ef6b5a26ea46c8f1338172b3245493`.

Historical S11A, its Accepted S9J live-byte successor correction, and S11B each still have an
Accepted Slice Contract and Accepted final verification receipt.
Historical S11A hashes are never rebaselined: S9J owns its correction, while
S11B is the latest authority for every path in its final `implementation_artifacts` map, including
the V2 chat route and dependency module. Remaining non-superseded S11A paths still compare to
historical S11A. S2C Task 2.8 external
human review is not a Ready or acceptance gate for S11C: Task 11.2 consumes the already-Accepted
Task 2.7 structural claim-level case-contract tests, not prose gold or an external quality judgment.

S11C may close Tasks `11.1`-`11.5` only together, after all required checks exist and one independent
review reports `Critical=0` and `Important=0`. Minor/YAGNI findings are recorded and non-blocking.
Before that point it changes no OpenSpec checkbox or formal ledger.

## Accepted dependency boundary

S11C consumes, but never repairs or reinterprets:

- Historical Accepted S11A plus Accepted S9J: S11A owns the original V2 chat/session contract and
  S9J explicitly owns its corrected public-copy service/owner bytes; their receipt hashes remain
  immutable historical/successor evidence;
- Accepted S11B: candidate V2 admin/browse/feedback surface, explicit-target EvidenceLanding CLI,
  sanctioned smoke caller, candidate import quarantine, the versioned legacy-consumer inventory,
  and the final live artifact map that supersedes earlier path hashes where explicitly listed;
- Accepted S2C2 / Task 2.7: machine-validatable required/forbidden claims and entities, allowed
  variants, source snapshots/as-of, coverage policy, and stage expectations, with prose reference
  answers remaining review-only;
- accepted disposable PostgreSQL, release-publication, index-projection, read/answer trace-replay,
  and no-online-write owners from S3-S10.

If historical S11A, successor S9J, or S11B authority becomes absent, stale, non-Accepted, or
disagrees with the latest-Accepted-owner-per-path file hashes, S11C returns to Specified. S11C does not compensate
with local production changes or silently rebaseline any predecessor.

## Immutable S11B inventory authority

S11B acceptance freezes one exact inventory path, raw-byte SHA-256, category counts, disposition
counts, and the exact sorted `s11c_disposition` entries/count in its verification receipt. S11C
copies that authority into its own evidence by recording:

```text
accepted_s11b_receipt_path
accepted_s11b_receipt_sha256
base_inventory_path
base_inventory_receipt_json_pointer
base_inventory_sha256
base_category_counts
base_disposition_counts
base_s11c_disposition_entries
```

S11C never edits, canonicalizes, regenerates, sorts, copies over, or accepts a new version/hash of
the Accepted inventory. A read-only byte check may prove that the original path still equals the
frozen S11B hash; any mismatch is a predecessor regression and a stop condition.

Disposition work lives only in
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/disposition-overlay-v1.json`. The overlay
records the frozen base receipt/hash and resolves each base `s11c_disposition` inventory entry
exactly once. It cannot add an uninventoried legacy path or alter an existing inventory category,
reason, replacement, or disposition.

The overlay schema is intentionally small:

```json
{
  "schema_version": "canonical-v2-s11c-disposition-overlay-v1",
  "accepted_s11b_receipt_sha256": "<exact Accepted receipt hash>",
  "base_inventory_receipt_json_pointer": "<exact pointer in the Accepted receipt>",
  "base_inventory_sha256": "<exact Accepted inventory hash>",
  "entries": [
    {
      "inventory_category": "legacy_scripts",
      "inventory_path": "exact/repository-relative/path.py",
      "disposition": "replaced_owner_passed|reference_only_quarantined",
      "replacement_owner_nodeids": ["<exact pytest nodeid>"],
      "reason": "<bounded evidence-based reason>"
    }
  ]
}
```

Every overlay entry requires at least one exact passing owner nodeid. A functional replacement uses
`replaced_owner_passed`; an intentionally absent legacy behavior uses the quarantine/import owner as
`reference_only_quarantined`. Unknown dispositions, empty owner sets, duplicate entries, globs, and
unresolved base entries reject acceptance.

The frozen base inventory itself remains authoritative for already-final dispositions. A ledger row
with `retired_replaced` may directly bind the same exact `(top-level category, path/module)` entry
whose frozen disposition is `replaced`; `retired_reference_only` may directly bind one whose frozen
disposition is `reference_only`. Only a base entry whose frozen disposition is
`s11c_disposition` is resolved through the overlay, where `replaced_owner_passed` maps to
`retired_replaced` and `reference_only_quarantined` maps to `retired_reference_only`. Every path
still requires an exact passing recorded-JUnit owner, and the protected accepted/S11/candidate/
contract/trace/release/index/write-safety failure classes remain ineligible for retirement. The
current frozen counts are `reference_only=136`, `replaced=5`, and `s11c_disposition=0`, so the
correct overlay is empty and must not duplicate 141 already-final entries.

## Retired-failure reconciliation

Task 11.4 permits unrelated or intentionally retired failures to be recorded separately; it does
not permit `--ignore`, broad `-k not ...`, known-failure lists, skip/xfail insertion, swallowed exit
codes, or prose assertions that a failure is harmless.

S11C captures each required broad command into a distinct JUnit XML file under `s11c/junit/` and
records its real exit code. It also records the exact collected pytest nodeids for those explicit
file/suite inputs. The S11C-local wrapper installs the Accepted S11B early
no-external guard before initial conftests, clears the same 49 sensitive names, blocks
socket/psycopg/dotenv effects, retains guard/cleanup receipts, and uses signature v3. Admin
collect/run uses exact marker `not requires_classifier_llm` and the sole deselected node
`tests/test_classifier_benchmark.py::test_classifier_benchmark`; naked broad pytest is forbidden.
The wrapper produces exactly two ledger inputs: Admin no-external and Canonical V2 predecessors
excluding only the exact S11C acceptance file. The validator consumes only artifact paths explicitly
declared by the ledger; it never globs evidence directories. The ledger raw-hash-binds the guarded-
wrapper receipt, whose run set remains exactly those two real-subprocess partitions with frozen
Accepted S11B authority, terminal capture, Admin selection, and cleanup. The ledger may additionally
contain Task 11.2 targeted runs, but each extra run must exit `0`, contain only passing cases, and
cannot contribute a failure/disposition row. After ledger completion, the focused
S11C owner runs in a separate `s11c/focused/` namespace. A post-process receipt written after that
process exits proves `1 passed` and the exact predecessor-plus-focused file-set union; focused
artifacts are never validator inputs and immutable capture paths are never overwritten.
The immutable guarded receipt, failure ledger, and broad JUnit bytes are supplemented rather than
rewritten. `guarded-execution-provenance-v1.json` raw-hash-binds all four sources and derives exact
UTC start/finish from each JUnit testsuite timestamp plus duration; the aggregate validator
recomputes the derivation. `predecessor-reruns-v2.json` preserves and raw-hash-binds v1 while adding
exact repository-root cwd, strict UTC start/finish, launcher argv, sanitized environment delta, and
fresh raw stdout/stderr hashes for all four unchanged Accepted commands.
The failure ledger must have a one-to-one row for every JUnit `<failure>` or
`<error>` and no extra row:

```json
{
  "schema_version": "canonical-v2-s11c-retired-failure-ledger-v1",
  "base_inventory_sha256": "<frozen S11B value>",
  "runs": [
    {
      "run_id": "<stable run ID>",
      "command": ["<exact argv tokens>"],
      "exit_code": 0,
      "junit_xml_path": "<exact repository-relative path>",
      "junit_xml_sha256": "<raw-byte hash>",
      "collected_nodeids_path": "<exact repository-relative path>",
      "collected_nodeids_sha256": "<raw-byte hash>"
    }
  ],
  "failures": [
    {
      "run_id": "<run ID>",
      "nodeid": "<exact collected pytest nodeid>",
      "outcome": "failure|error",
      "normalized_failure_signature_sha256": "<deterministic hash>",
      "inventory_category": "legacy_scripts",
      "inventory_path": "exact/repository-relative/path.py",
      "baseline_signature_sha256": null,
      "scope_owner_nodeid": null,
      "replacement_owner_nodeids": ["<exact passing nodeid>"],
      "disposition": "retired_replaced|retired_reference_only|unrelated_preexisting",
      "reason": "<bounded evidence-based reason>"
    }
  ]
}
```

Signature schema `canonical-v2-s11b-baseline-signature-v3` changes only CRLF to LF, replaces the
guarded-wrapper receipt's exact effective run basetemp root with `<pytest-tmp>/` first, and replaces
the exact repository root with `<repo>/` second; it retains the exception class, JUnit message,
traceback frames, assertion diff, filenames, and line numbers. Declared command basetemp remains
independent exact argv evidence. The effective root must match
`guard_preflight.pytest_temp_roots[run_id]["run"]` and a terminal run-mode child receipt inside the
owned temp root, with cleanup/session-finished/unconfigured true. The signature is SHA-256 over
`outcome + "\n" + normalized message + "\n" + normalized body`. No regex may erase
IDs, values, error types, assertions, or failure frames.

Inventory identity is the exact `(top-level category, path/module)` pair already present in S11B;
S11C does not require or invent a new ID field. `retired_replaced` and `retired_reference_only`
require that same pair in the already-final frozen base disposition, or, only for base
`s11c_disposition`, in the exactly mapped overlay disposition, plus at least one passing
replacement/quarantine owner from recorded JUnit. `unrelated_preexisting` uses null inventory
fields and requires an exact signature
already frozen in the Accepted S11B receipt/evidence plus an explicit passing non-consumer
`scope_owner_nodeid`, and requires independent-review acceptance. If S11B froze no exact baseline,
the disposition is unavailable. It cannot cover a candidate import, route, data-contract, trace,
write-safety, release, index, or S11 owner failure. Any unaccounted, changed-signature, missing-owner,
or accepted-behavior failure blocks S11C.

## Task 11.2 evidence boundary

Task 11.2 is satisfied structurally, not by judging product prose. Required evidence includes:

1. Accepted S2C Task 2.7 schema/corpus owners:
   `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/test_claim_level_case_contract.py` and
   `test_claim_level_corpus_migration.py`;
1. S11A/S11B public HTTP/session/admin/quarantine/CLI owners;
1. accepted interface, scenario, and trace-replay owners through public deep-module seams;
1. the explicit disposable PostgreSQL owner matrix with target identity and backup gate; and
1. release-publication and release/index-projection adapter owners, including exact parity and
   no-active-index-mutation checks.

S11C does not execute or require S2C Task 2.8 external human review, human calibration, LLM judging,
prose/reference-answer matching, or real-provider quality acceptance. Those remain S8/S9/S12
acceptance-oracle work. S2C's external gate is therefore not a global or S11C blocker.

The Task 11.2 PostgreSQL matrix uses one S11C-local lifecycle receipt. It revalidates the existing
Accepted marker-owned `canonical-v2-s6c-pg-20260712` container/base authority, including
`network=none`, no published ports, the base marker, and backup gate. It requires fixed database
`miroflow_canonical_v2_s4c_disposable` to be absent before creation, creates it only inside that
container, installs exact marker
`miroflow:destructive-target:v1:disposable:miroflow_canonical_v2_s4c_disposable`, passes only the
four `CANONICAL_V2_TEST_*` values to the owner matrix, and stores no password or credential-bearing
DSN. It deletes the database only when this attempt created it and the marker still matches, then
records final absence. Any pre-existing fixed database or identity/cleanup mismatch is fail-closed.
The aggregate validator consumes that fixed receipt and cross-binds its Accepted S10O receipt SHA,
container/base/target identity, exact four provided environment names, `122` passing cases/JUnit
hash, cleanup invariants, and final absence to ledger run `disposable-postgres`.

## OpenSpec task mapping

- **11.1:** Accepted S11A/S11B receipts plus machine-validated aggregate
  `predecessor-reruns-v2.json` exact unchanged-command/cwd/UTC records, preserved-v1 hash binding,
  and applicable broad-JUnit cross-links for public HTTP/admin/CLI owners prove every sanctioned
  consumer uses the deep-module interfaces.
- **11.2:** structural Task 2.7, interface/scenario/trace replay, disposable PostgreSQL, and
  release/index adapter owners replace implementation-coupled evidence without prose gold.
- **11.3:** frozen S11B inventory, zero unresolved overlay entries, candidate import/route guards,
  and passing replacement/quarantine owners prove legacy behavior is removed or quarantined.
- **11.4:** explicit safe-target broad commands, raw JUnit, recomputed UTC provenance, exact
  nodeids/signatures, and the complete failure ledger distinguish passing, retired, and truly
  unrelated outcomes without swallowing.
- **11.5:** one independent review verifies no accepted behavior depends on an implementation detail
  represented by an overlay or failure-ledger disposition.

Only after all five mappings are complete and review is `C0/I0` may the five task checkboxes change
atomically. The acceptance receipt records the exact live ledger before and after, with a delta of
five and no other checkbox change.

## File and effect boundary

S11C execution may create only:

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/*` acceptance evidence; and
- `apps/miroflow-agent/tests/canonical_v2/test_consumer_acceptance_contract.py`.

No production file, existing test, S11A/B artifact, S2C artifact, accepted inventory, schema,
migration, source, active pointer, or runtime configuration is edited. The sole database-content
exception is the exact S11C-owned transient PostgreSQL target described above. S11C may create its
local lifecycle receipt, exact predecessor-rerun receipts, broad-JUnit cross-links, focused/postflight
evidence, and final verification receipt. Disposable index/test-local candidate adapters remain
explicitly gated and are cleaned up. Original PostgreSQL/Milvus/forensic sources, base database,
owned container, and every other database remain unchanged.

## Ready and acceptance decision

### Superseded pre-Ready evidence — 2026-07-21

The evidence below remains historical dependency evidence, but its Ready authorization and document/
wrapper hashes are no longer execution authority. A fresh contract-alignment review and new hashes
are required before Task 3 or any effectful capture.

The accepted authority chain and latest-owner-per-path rule were rechecked against live bytes:

| Authority | Accepted at | Contract SHA-256 | Receipt SHA-256 |
| --- | --- | --- | --- |
| historical S11A | `2026-07-20T19:56:07Z` | `ecf8e53a2d44801f561becbf97a3502fcdfb4ddc72cbff3396c0d5ea7398abd4` | `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3` |
| S9J successor | `2026-07-21T09:57:11Z` | `7be6d549dd126f653cb36645ed339f9fb0245a06337558a3fb5041c0d8d0344f` | `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc` |
| S11B | `2026-07-21T12:54:16Z` | `e0568f9d046310b5cd5648e2fbb068875ae95580370154841ca1f59244d1ed32` | `cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945` |

S11C consumes exact commands and final changed-file hashes from those immutable receipts. The
complete current S11B live map is the receipt's `/implementation_artifacts`; it includes chat route
`f91be4ffcebaf2a6f091ddc09b798f56357b8bf8e38be803b68c80f14736a35a`, dependency module
`e1f4aa70d6ef84649fda5571418860bfdccf0c1dd9b57bb9c3c209cfa834fa8e`, and chat service
`15385247c9cf780e189651c97d15a9ad91fb6a5f8ef5f201bebcc19bb2814b82`. Non-superseded S9J and
remaining historical S11A paths also match their final receipt maps. No predecessor is rebaselined.

The S11B receipt JSON pointer `/legacy_consumer_inventory/sha256` resolves to
`c5a151b82cf308ec8504c31c10f6e6d997a3286ef18613d530088314a7f8f940`, matching the raw inventory
bytes. Category counts are `legacy_modules=22`, `legacy_scripts=85`,
`retired_frontend_routes=22`, `retired_http_routers=12`, and `sanctioned_entrypoints=6`;
dispositions are `reference_only=136` and `replaced=5`. The exact `s11c_disposition` set is empty
with count `0`, so the later overlay must be empty rather than inventing entries.

Accepted S2C2/Task 2.7 authority is the legacy slice contract SHA-256
`3ce0bf7425e0bfb63c88da62dc22500f683c7aaa2f89d1f460ef4e53b1cfbac7` plus its verification
section. Its schema/corpus/snapshot/manifest raw hashes are respectively
`0e6347e857dee2270cfca8acf16b0f89347521b531ce703d3e3e574230775c9d`,
`75ff02e0610b93274eba530994a3b04c2bc2a427df9db2ae6d07aaee690a6668`,
`85c1e4c1660e151526d54f9b1416917782f961b318091550bb3ef8042d16e253`, and
`fbc95a25fc662ac9b3c32491a45ef40953a50643888759ee1d438529f00d682f`; manifest content identity is
`df3a7b09a4f049ac6b34bfd1f128329dc9e7effb3ec61398317026778dc0c8ff`. The structural owners are
`s2c/test_claim_level_case_contract.py` and `s2c/test_claim_level_corpus_migration.py`. Task 2.8
remains unchecked and is not an S11C gate.

The sole pre-Ready bootstrap added only `s11c/capture_guarded_partitions.py` SHA-256
`dec9013165991ec139170278e4124a001e1071dae9b09f97aad7e9a544d4e5c9` and its owner
`s11c/test_capture_guarded_partitions.py` SHA-256
`52a0c04cc5cb643e926cfbd9046823eaabc49ed38bb824b1fa2105a4147cc62f`. Initial RED was `1 xfailed`;
forced RED was the exact `_MissingS11CGuardedPartitionWrapper` failure before any runner call.
Review-driven REDs reproduced selection/runner/output ownership, hash-to-use, and post-link ABA
defects. Final focused GREEN is `6 passed`; Ruff check/format, `py_compile`, and Pyright (`0 errors, 0 warnings, 0 informations`) pass. No broad partition ran. Spec review and the final targeted
quality closure are both `C0/I0`. One combined pre-existing-sentinel test-quality Minor
is nonblocking because exact post-link ABA and no-overwrite owners independently cover executable
ownership.

The pre-acceptance live ledger was `65/80`; Tasks `11.1`-`11.5` were all unchecked. The frozen
pre-acceptance `tasks.md` and `acceptance.md` SHA-256 values were
`87eb7c1e6d9e5b80e535cb94398f42798cdf4f3c83fb818011d0948519e32e54` and
`1943943ee6fbc50b33357db1cceb987af93eba129042e6e4d6edfb68c9d5261f`.

After the former Ready transition, the first Task 2 checkpoint adds only
`apps/miroflow-agent/tests/canonical_v2/test_consumer_acceptance_contract.py` at SHA-256
`d98e1b5a127e6c6dcf5f0f948ac9b521b502d4adb17512a2fb9b68afcefe99a0`. The exact public owner is
strict-xfailed before candidate import, database connection, source read, or legacy import while
overlay, ledger, collected-nodeid, or JUnit evidence is absent. Normal RED is `1 xfailed`; forced
`--runxfail` is exactly one `_MissingS11CAcceptanceEvidence` failure. Ruff check/format,
`py_compile`, and Pyright (`0 errors, 0 warnings, 0 informations`) pass. The finite ledger/JUnit/
authority validator remains Task 2 In Progress; no evidence is fabricated and no broad command ran.

The former lean pre-Ready review reported `Critical=0 / Important=0 / Minor=1 / YAGNI=0`. The reviewed
Specified hashes are audit `b72f3371566eb662c5cd8b4a22f2154eae40d6bca460bb24b8beedfd0983a92a`,
plan `867fe8d8cd259750dffaf1683b1189e1ca28f23bb36bfc6ec555f4e83d866df5`, and contract
`6b78203fa65a8325ac43c824866ce3571bb91eed181c8ddd1c5015284da471df`. S11C transitioned to Ready
at `2026-07-21T15:02:07Z`, but that authorization was superseded at
`2026-07-21T16:35:09Z` by the four-item contract-amendment gate. No OpenSpec task, acceptance,
production, source, original database/index, or active-pointer change occurred.

Re-Ready authorization requires historical Accepted S11A, Accepted S9J successor authority, and
Accepted S11B contracts/receipts; exact latest-owner-per-path/receipt/inventory hashes; a GREEN S11C-local guarded-
capture wrapper owner implementing the two-partition boundary; the aligned finite validator;
strict OpenSpec; document/scope checks; and one lean contract-alignment review with zero open
Critical or Important findings. New reviewed hashes and UTC time are recorded without changing
tasks.

That re-authorization completed at `2026-07-21T17:42:54Z`. Contract-alignment review and final
validator quality review both reported `Critical=0 / Important=0`; validator checks were
`46 passed, 1 xfailed`, exact normal RED was `1 xfailed`, forced RED was the sole exact sentinel,
Pyright was `0 errors`, the wrapper owner was `6 passed`, and strict OpenSpec, diff, Ruff, and compile
checks passed. Task 3 and later are authorized without changing an OpenSpec task.

The later final-evidence review opened one Important traceability finding and therefore superseded
that authorization for Candidate progression. RED reproduced six missing/tampered cwd, UTC, and
source-hash cases. The repair reached focused aggregate `1 passed`, full validator `55 passed`, and
capture owner `2 passed`; Ruff, format, compile, and Pyright also pass. The authoritative v2 receipt
contains four exit-zero reruns from exact cwd
`/home/longxiang/MiroThinker/.worktrees/canonical-v2-s2`. A duplicate non-authoritative capture was
started after the first long-running tool session was mistaken for completed; it reran the same
effect-free pytest commands, then failed at exclusive create because the authoritative receipt
already existed. It produced no receipt and overwrote no v1, v2, guarded, ledger, JUnit, source,
database, index, pointer, or predecessor artifact. Traceability execution was re-authorized at
`2026-07-21T18:42:28Z`; Candidate and Accepted closure followed only after the final independent
evidence and protected-scope reviews returned `C0/I0`.

Accepted evidence includes the aggregate test, exact owner reruns, complete JUnit/ledger/overlay
validation, explicit disposable-target checks, source/pointer invariants, generated cleanup, and
independent evidence/protected-scope reviews at `C0/I0`. Tasks `11.1`-`11.5` changed together at
`2026-07-21T19:10:41Z`; the resulting ledger is `70/80`.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md` Tasks 11.1-11.5;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/convergence-plan-remaining-24-2026-07-20.md`;
- corrected S11A/S11B audits, plans, contracts, and eventual Accepted receipts;
- Accepted S2C2/Task 2.7 contract and structural artifacts;
- current public interface/PostgreSQL/release/index owners as execution evidence only.

This audit changes no production code, test, Accepted artifact, OpenSpec checkbox, formal ledger,
database, index, source, pointer, Commit, Push, PR, Archive, promotion, or Cutover.
