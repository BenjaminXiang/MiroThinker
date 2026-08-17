# S11C Aggregate Consumer Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` only after this plan becomes Ready, except for the explicitly scoped
> Task 1 guarded-wrapper RED/GREEN bootstrap required to reach Ready. Use
> `superpowers:test-driven-development` for the acceptance-artifact RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. Steps use checkbox
> syntax for tracking. One writer owns the aggregate evidence. Do not Commit.

**Goal:** Accept Tasks 11.1-11.5 together by proving that every sanctioned consumer uses Canonical
V2 interfaces, every retired dependency is exactly reconciled, and all broad checks run against
explicit safe targets without changing production behavior.

**Architecture:** Add one pure acceptance-contract test. It validates the immutable Accepted S11B
inventory hash, a separate S11C disposition overlay, exact JUnit/nodeid/failure-signature accounting,
replacement owner results, and required Task 11.2 structural/PostgreSQL/release-index evidence. All
other work is read-only rerun/evidence collection; there is no production delta.

**Tech Stack:** Python 3.12, pytest/JUnit XML, JSON, SHA-256, existing FastAPI/Canonical V2 owners,
disposable PostgreSQL fixtures, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan is **Accepted** at `2026-07-21T19:10:41Z` after Candidate at `2026-07-21T19:05:17Z`. The former Ready authorization at
`2026-07-21T15:02:07Z` remains superseded. The execution re-authorization
at `2026-07-21T17:42:54Z` was superseded for Candidate progression by one Important traceability
finding. That finding is closed by a v2 predecessor receipt with exact repository-root cwd and UTC,
plus a raw-hash-bound broad-JUnit provenance supplement whose UTC window is recomputed by the
validator. Required evidence, independent review, generated cleanup, and protected-scope review
are complete at `Critical=0 / Important=0`; Tasks `11.1`-`11.5` closed atomically and the formal
ledger moved `65/80 -> 70/80`.

### Traceability correction checkpoint

- [x] Observe six exact validator REDs for missing/tampered predecessor cwd, guarded UTC, and
  source hashes; each failed because the former validator did not reject the tamper.
- [x] Add the evidence-only exclusive-create capture helper/owner and reach `2 passed`.
- [x] Preserve `predecessor-reruns-v1.json`; create `predecessor-reruns-v2.json` by rerunning all
  four unchanged Accepted command strings from the exact repository-root cwd with raw
  stdout/stderr hashes and strict UTC start/finish.
- [x] Preserve all Task 5 broad artifacts; create `guarded-execution-provenance-v1.json` by binding
  their raw ledger/guard/JUnit hashes and deriving UTC from exact JUnit timestamp plus duration.
- [x] Reach focused aggregate `1 passed`, full validator `55 passed`, capture owner `2 passed`, and
  Ruff/format/compile/Pyright GREEN without changing an OpenSpec checkbox.
- [x] Record the duplicate non-authoritative rerun attempt caused by an orchestration-session
  ambiguity: it reached the exclusive-create `FileExistsError` after the authoritative receipt was
  already written and did not overwrite that receipt or any predecessor/broad artifact.

The exact repair hashes are validator
`3924a00af6dbe183f0a1199ed7b9977b5475dad3ee558b4fa4fd7758f9ca62bb`, helper
`a1bbf4d60ee2e73aee93a27ff3d75a6d94526f08d4701c243c40ca204da7bdf4`, owner
`060c7ab2979bb9d69b6a30533660205d226ef5bb660cd62897616ddff171db8c`, provenance
`8b307160f9f1231896d11f43d71b06daed329824a50f3255a127d922aa35f467`, preserved v1
`84507b7c3fd6a441547922cfc7012c58a74b6a11c82ec001ffe8e300ffc5eb11`, and authoritative v2
`6043e991ff2971aba8bb5a1492261be302412aab1cb272b9027ac24009282d8d`.

The earlier amended plan, contract/audit, two-partition wrapper/owner, and finite validator received
independent contract and quality reviews at `Critical=0 / Important=0`. Their historical
pre-authorization hashes remain recorded in the Slice Contract:

- [x] Historical S11A, successor S9J, and S11B Slice Contracts/final receipts say Accepted. Verify
  live bytes by latest Accepted owner per path: S11B `implementation_artifacts` first, then any
  non-superseded S9J correction, then remaining historical S11A paths. No receipt is rebaselined.
- [x] The S11B receipt supplies one exact inventory path/hash, category/disposition counts, and exact
  sorted `s11c_disposition` entries/count.
- [x] A reviewed S11C-local guarded-capture wrapper reuses the Accepted S11B early
  socket/psycopg/dotenv/environment/receipt/cleanup invariants, freezes Admin marker
  `not requires_classifier_llm`, and records the sole deselected classifier benchmark. Naked broad
  pytest commands are forbidden until this wrapper is GREEN.
- [x] One lean S11C audit/plan/contract review reports zero open Critical/Important findings.
- [x] Minor/YAGNI findings are recorded as non-blocking without another theoretical review loop.
- [x] Strict OpenSpec and document/scope checks exit `0`.
- [x] Reviewed Specified hashes and a UTC timestamp are recorded in the Ready transition.
- [x] Amend the evidence workflow to remove focused self-reference, allow direct frozen-base retired
  bindings, separate exact predecessor reruns from broad JUnit, and authorize one marker-owned
  S11C-local transient PostgreSQL target. Re-freeze hashes and obtain fresh `C0/I0` before effects.

Accepted S2C Task 2.7 is evidence for Task 11.2. S2C Task 2.8 external human review, prose-gold
judgment, and real-provider quality acceptance are not S11C Ready/acceptance gates. No Commit, Push,
PR, Archive, promotion, production-like Cutover, original-source write, or destructive cleanup
belongs to this plan.

## File map

### Only implementation/test delta

- Create `apps/miroflow-agent/tests/canonical_v2/test_consumer_acceptance_contract.py`: one atomic
  validator for Accepted predecessor identities, frozen inventory authority, overlay completeness,
  exact JUnit/failure-ledger reconciliation, replacement-owner passes, Task 11.2 evidence families,
  and zero unresolved accepted-behavior failure.

### S11C evidence files

- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/capture_guarded_partitions.py`
  and `test_capture_guarded_partitions.py`: S11C-local parent/wrapper and fail-closed owner reusing
  the exact Accepted S11B early guard/validators by frozen hash without changing application script
  discovery or the Accepted artifact.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/capture_execution_traceability.py`
  and `test_capture_execution_traceability.py`: S11C-local evidence-only capture helper and
  fail-closed owner for the predecessor v2 receipt and guarded UTC provenance supplement.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/disposition-overlay-v1.json`.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/retired-failure-ledger-v1.json`.
- Preserve `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/predecessor-reruns-v1.json`
  and create `predecessor-reruns-v2.json` with the exact four Accepted-command rerun records,
  repository-root cwd/UTC provenance, v1 raw-hash binding, and applicable broad-JUnit cross-links.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/guarded-execution-provenance-v1.json`
  without overwriting broad artifacts; bind ledger/guard/JUnit raw hashes and derive UTC windows
  from exact JUnit testsuite timestamp plus duration.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/collected/*.txt` with exact
  `pytest --collect-only` nodeids for each explicit test partition.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/*.xml` from the exact
  required commands.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/focused/*` only after ledger
  completion, plus a postflight receipt proving focused success and exact file-set union. Focused
  artifacts are not validator inputs.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/disposable-postgres-target-receipt.json`
  for the one transient marker-owned database lifecycle; never record a credential-bearing DSN.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/verification-receipt.json` only
  after Candidate evidence exists.
- Update only this audit/plan/contract and S11C-local review/evidence before acceptance.

Do not modify production, any existing test, Accepted S11A/B/S2C artifact, the S11B inventory,
schema/migration, source, index, active pointer, or S9/S10/S12 artifact. At final acceptance only,
the authorized OpenSpec/status evidence may record the atomic five-task closure.

## Task 1: Confirm Accepted dependencies and freeze Ready

- [x] Read the historical S11A, successor S9J, and final S11B contracts/receipts directly. Record
  their paths, raw-byte SHA-256, Accepted timestamps, exact commands, and authority-scoped final
  changed-file hashes. Stop on any disagreement; never compare a path to an earlier owner when a
  later Accepted receipt explicitly supersedes that path.
- [x] Resolve the exact S11B receipt JSON pointer for the accepted inventory hash. Record, without
  rewriting, its inventory path, raw-byte hash, category/disposition counts, and exact sorted
  `s11c_disposition` entries/count.
- [x] Read the inventory raw bytes once for verification and require their SHA-256 to equal the
  receipt value. Do not parse-and-reserialize, sort, normalize, copy over, edit, or generate a new
  inventory version/hash.
- [x] Confirm S2C2 is Accepted and Task 2.7 is checked. Record the accepted schema/corpus/manifest
  hashes and the exact structural owner paths. Do not require Task 2.8 or read prose as truth.
- [x] Capture the live OpenSpec ledger and confirm Tasks 11.1-11.5 are all unchecked.
- [x] As the sole pre-Ready implementation exception, write
  `s11c/capture_guarded_partitions.py` and `s11c/test_capture_guarded_partitions.py` through an exact
  fail-closed RED/GREEN. The owner must prove early Accepted-S11B guard installation, the same 49
  present-empty sensitive names, `PYTHON_DOTENV_DISABLED=1`, socket/psycopg/dotenv blocking,
  signature v3, exact per-run collect/run basetemp mapping, terminal receipt/cleanup, Admin marker
  `not requires_classifier_llm`, and the sole deselected classifier benchmark. Do not run a broad
  partition in Task 1.
- [x] Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`.

- [x] Complete one lean pre-Ready review. Repair open Critical/Important findings only; record
  Minor/YAGNI as non-blocking.
- [x] Freeze reviewed hashes and mark S11C Ready. Do not change production, tests, `tasks.md`, or
  acceptance evidence in this task.

## Task 2: Write and observe the exact acceptance-artifact RED

**Create:** `apps/miroflow-agent/tests/canonical_v2/test_consumer_acceptance_contract.py`

- [x] Add an exact `_MissingS11CAcceptanceEvidence` sentinel and one atomic owner:

```python
def test_s11c_reconciles_all_consumer_evidence_without_legacy_dependency() -> None:
    evidence = load_s11c_acceptance_evidence()
    validate_s11c_acceptance_evidence(evidence)
```

- [x] Before importing the candidate app, connecting to PostgreSQL, reading source data, or loading
  a legacy module, resolve these S11C-local artifacts:

```text
disposition-overlay-v1.json
retired-failure-ledger-v1.json
guarded-partitions-receipt.json
predecessor-reruns-v1.json
predecessor-reruns-v2.json
guarded-execution-provenance-v1.json
disposable-postgres-target-receipt.json
only each ledger run's exact collected_nodeids_path
only each ledger run's exact junit_xml_path
```

While any is absent, the exact owner is strict-xfail with
`_MissingS11CAcceptanceEvidence`. The test reads only repository evidence and predecessor receipts;
it never launches pytest, writes a report, or mutates inventory/runtime state.

- [x] Implement helpers in the same test file with these finite rules:
  - SHA-256 is over raw bytes;
  - overlay entries match base `(top-level category, path/module)` keys whose disposition is
    `s11c_disposition`, exactly once;
  - overlay dispositions are only `replaced_owner_passed` or `reference_only_quarantined` and have
    non-empty exact owner nodeids;
  - JUnit testcases map uniquely to a nodeid in the matching collected-nodeids file;
  - failure normalization uses `canonical-v2-s11b-baseline-signature-v3`: change only CRLF, replace
    the guarded-wrapper receipt's effective run basetemp root with `<pytest-tmp>/` first, replace the
    exact repository root with `<repo>/` second, then hash `outcome`, normalized message, and
    normalized retained body separated by LF; the declared argv basetemp remains a separately
    validated command field;
  - every JUnit failure/error has exactly one ledger row and every ledger row has exactly one JUnit
    failure/error;
  - every retired row maps either directly to the same frozen inventory key with final disposition
    `replaced`/`reference_only`, or, only for a base `s11c_disposition`, to the corresponding overlay
    disposition; every replacement nodeid is a passing testcase in recorded JUnit;
  - `unrelated_preexisting` requires the exact recorded baseline signature and cannot name an S11,
    candidate-import/route, contract, release/index, trace, or write-safety owner;
  - all required evidence-family labels are present: `s11a_http_session`, `s11b_admin_quarantine`,
    `s2c_task_2_7_structural`, `interface_scenario_trace`, `disposable_postgres`, and
    `release_index_adapter`.
- [x] Run normal RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_consumer_acceptance_contract.py::test_s11c_reconciles_all_consumer_evidence_without_legacy_dependency -q
```

Expected: exactly `1 xfailed`, zero failure/error/XPASS.

- [x] Run forced RED with `--runxfail`. Expected: exactly one failure at
  `_MissingS11CAcceptanceEvidence` before candidate import, database connection, source read, legacy
  import, or external effect.

## Task 3: Create the separate inventory disposition overlay

**Create:**
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/disposition-overlay-v1.json`

- [x] Copy only the Accepted S11B receipt SHA-256, its exact inventory-hash JSON pointer, and the
  frozen inventory SHA-256 into the overlay header. These values are not recalculated authorities.
- [x] Add exactly one overlay entry per base inventory entry recorded as `s11c_disposition`; preserve
  its top-level category and exact path/module as the identity key, and choose only:
  - `replaced_owner_passed` when a sanctioned V2 owner exercises the replacement behavior; or
  - `reference_only_quarantined` when an import/route/command guard proves the behavior is intentionally
    absent from every accepted path.
- [x] Give each overlay entry at least one exact pytest replacement/quarantine owner nodeid. Use no
  file glob, test prefix, `-k` fragment, URL pattern, or prose-only owner.
- [x] Require overlay entry count and `(category, path/module)` set to equal the frozen S11B
  `s11c_disposition` count/set.
  Duplicate, missing, extra, or unresolved entries stop execution.
- [x] Use the same read-only raw-byte verification to confirm the inventory still equals the frozen
  Accepted value. Do not edit/reserialize it or re-hash/rebaseline it as a new inventory authority.
- [x] Record that the frozen inventory currently contains `reference_only=136`, `replaced=5`, and
  `s11c_disposition=0`; therefore the correct overlay has an empty `entries` array. Do not copy the
  141 already-final base entries into it.

## Task 4: Run the required Task 11.2 owner families

Task 4A/4C/4D/4E commands record exact argv, exit code, UTC time, collected-nodeid bytes/hash, JUnit
bytes/hash, and sanitized target identity in S11C-local evidence. Task 4B Accepted commands instead
run unchanged and receive exact rerun receipts; broad JUnit provides a separate node-level
cross-proof where applicable. No command uses `--ignore` for a predecessor failure, `-k not`,
known-failure plugins, runtime xfail, `|| true`, or a prose-gold evaluator.

### 4A. S2C Task 2.7 structural case contracts

- [x] Run exactly the Accepted structural owners:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/test_claim_level_case_contract.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/test_claim_level_corpus_migration.py \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/tmp/s2c-task-2-7/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/s2c-task-2-7.xml -q
```

Expected: exit `0`, no xfail/XPASS. Record schema/corpus/manifest hashes. Do not run S2C external
human review, prose matching, or real-provider judging for S11C.

### 4B. S11 public consumer owners

- [x] Rerun every final S11A and S11B command exactly from their Accepted receipts, including HTTP/
  session, admin/browse/feedback, EvidenceLanding CLI, smoke caller, inventory/quarantine/import,
  static-export ordering, unknown-API `404`, and protected-path/single-read owners.
- [x] Require each predecessor owner to pass with the same release/inventory identities and no
  skip/xfail/XPASS. A changed predecessor result blocks S11C; do not repair it here.
- [x] For each command, write an S11C-local exact-rerun receipt binding the Accepted receipt
  path/hash/pointer, authoritative command representation, cwd, sanitized environment delta, UTC,
  real exit code, and raw stdout/stderr hashes. Do not inject `--junitxml`, `--basetemp`, or any
  parameter into the Accepted command. If authority is a command string, bind that string/hash and
  the actual child argv; do not invent an historical argv array.
- [x] Preserve all four v1 records and store the current authoritative records in
  `predecessor-reruns-v2.json` with stable run IDs
  `s11b-focused-agent-owners`, `s11b-focused-admin-owners`, `s11a-predecessor-owner`, and
  `s10o-predecessor-owner`. Resolve and bind the exact Accepted S11B receipt JSON pointer/string;
  the aggregate validator rejects a missing/changed command, non-repository cwd, invalid UTC,
  nonzero exit, v1 hash drift, or incomplete applicable JUnit cross-link.
- [x] Cross-bind every applicable predecessor pytest nodeid to a passing broad-JUnit testcase by
  run ID and raw JUnit hash. CLI/script owners outside that collected universe rely on the exact
  rerun receipt unless they serve as retired replacement owners, which additionally require a
  recorded-JUnit pass.

### 4C. Interface, scenario, and trace replay

- [x] Run the public deep-module owner matrix:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_evidence_landing_replay_contract.py \
  tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py \
  tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py \
  tests/canonical_v2/test_knowledge_answer_grounding_contract.py \
  tests/canonical_v2/test_knowledge_answer_multiturn_contract.py \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/tmp/interface-trace/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/interface-trace.xml -q
```

Expected: exit `0`, no xfail/XPASS. These observable public seams replace implementation-coupled
legacy expectations.

### 4D. Disposable PostgreSQL

- [x] Create `s11c/disposable-postgres-target-receipt.json` by first revalidating the Accepted
  marker-owned `canonical-v2-s6c-pg-20260712` container/base authority, including immutable container
  identity, `network=none`, no published ports, base database/marker, and backup-gate identity.
- [x] Require fixed database `miroflow_canonical_v2_s4c_disposable` to be absent before creation;
  if present, stop rather than delete/reuse it. Create it only inside that owned container, install
  and re-read exact marker
  `miroflow:destructive-target:v1:disposable:miroflow_canonical_v2_s4c_disposable`, and pass only
  `CANONICAL_V2_TEST_DATABASE_URL`, `CANONICAL_V2_TEST_EXPECTED_DATABASE`,
  `CANONICAL_V2_TEST_TARGET_KIND=disposable`, and `CANONICAL_V2_TEST_BACKUP_GATE_ROOT` to Task 4D.
  Never use generic `DATABASE_URL`, `DATABASE_URL_TEST`, original `pgtest`, or a production-like
  target, and never store a password or full credential-bearing DSN in the receipt.
- [x] Run these exact files with `-n0`:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -n0 -W error \
  tests/canonical_v2/test_evidence_landing_postgres.py \
  tests/canonical_v2/test_canonical_decision_postgres.py \
  tests/canonical_v2/test_canonical_identity_postgres.py \
  tests/canonical_v2/test_domain_projection_postgres.py \
  tests/canonical_v2/test_relationship_projection_postgres.py \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/tmp/disposable-postgres/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/disposable-postgres.xml -q
```

Expected: exit `0`. Delete the fixed database only if this attempt created it and its exact marker
still matches; record final absence in the receipt. The base/container and original PostgreSQL stay
unchanged, and original PostgreSQL remains paused.

### 4E. Release and index adapters

- [x] Run:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_release_publication_interface.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/tmp/release-index-adapters/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/release-index-adapters.xml -q
```

Expected: zero unexpected failures; documented external skips are recorded but are not Task 11.2
evidence. Require exact release/projection/index parity, public release-bound adapters, rollback
authority, and zero active-index/original-Milvus mutation.

## Task 5: Capture broad JUnit and build the exact failure ledger

- [x] Revalidate and consume the already-GREEN Task 1 S11C-local guarded-capture wrapper before any
  broad command. Require its newly reviewed hash and owner result; do not reimplement it here. It may
  reuse the Accepted S11B plugin/validator code by exact hash but must not edit that Accepted
  artifact. Invoke only `capture_guarded_partitions(repository_root=<exact worktree root>)` and
  record the Python launcher argv; do not run either child command naked.
- [x] The guarded wrapper captures exactly two ledger-input partitions:
  - complete no-external Admin with the frozen marker; and
  - all discovered `tests/canonical_v2/test_*.py` except the exact new
    `test_consumer_acceptance_contract.py` path.
    It does not run the focused S11C owner. The validator loads only paths declared by the ledger and
    must never glob `s11c/junit`, `s11c/collected`, or `s11c/focused`. The ledger binds the raw
    `guarded-partitions-receipt.json` SHA-256.
- [x] The ledger may additionally contain Task 11.2 targeted owner runs. Require every non-guarded
  run to exit `0` with only passing JUnit cases; it cannot appear in the failure ledger. The guarded
  receipt itself remains exactly the two run IDs above and proves real subprocess capture, exact
  Accepted S11B authority, terminal post-process receipts, Admin selection, and cleanup.
- [x] Run `pytest --collect-only -q` for each exact admin/predecessor/Task-11.2 partition with a
  distinct explicit `s11c/tmp/<run-id>/collect/pytest` basetemp and save the complete nodeids under
  `s11c/collected/`. Admin collect uses exact marker `not requires_classifier_llm` and records only
  `tests/test_classifier_benchmark.py::test_classifier_benchmark` as deselected. Record collect/run
  roots separately; do not filter a node after collection.
- [x] Run the complete no-external admin-console suite and Canonical V2 predecessor partition with
  `--junitxml` paths under `s11c/junit/` and distinct exact `--basetemp` roots under `s11c/tmp/`.
  Record the run-id/root mapping and use signature schema
  `canonical-v2-s11b-baseline-signature-v3`: validate the declared argv basetemp independently, but
  normalize the guard receipt's exact effective run root before the repository root in both JUnit
  message and body. Cross-check that root against a matching run-mode terminal child receipt inside
  the owned temp root, and require cleanup/session-finished/unconfigured. Preserve real exit codes
  even when nonzero; do not weaken, skip, or rerun-select only passing nodes.
- [x] Preserve the guarded receipt, failure ledger, and both broad JUnit files byte-for-byte. Create
  one exclusive-create `guarded-execution-provenance-v1.json` that raw-hash-binds all sources and
  records UTC start/finish strictly derived from each JUnit testsuite timestamp plus duration. The
  validator independently recomputes both windows.

The following blocks freeze child argv for the guarded wrapper; they must not be run naked.

```bash
cd apps/admin-console
uv run pytest -o addopts='' -p no:cacheprovider \
  -m "not requires_classifier_llm" \
  tests \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/tmp/admin-no-external/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/admin-no-external.xml -q

cd ../miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2 \
  --ignore=tests/canonical_v2/test_consumer_acceptance_contract.py \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/tmp/canonical-v2-predecessors/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/junit/canonical-v2-predecessors.xml -q
```

The sole `--ignore` target is the S11C validator itself, which is run separately after its inputs
exist. The validator proves no other discovered file/node was excluded.

- [x] For every JUnit failure/error, map its file/class/name uniquely to one collected nodeid and
  compute the finite normalized signature. Create exactly one ledger row.
- [x] Permit only:
  - `retired_replaced`: matching frozen-base `replaced` entry, or base `s11c_disposition` plus
    overlay `replaced_owner_passed`, and a passing functional replacement owner;
  - `retired_reference_only`: matching frozen-base `reference_only` entry, or base
    `s11c_disposition` plus overlay `reference_only_quarantined`, and a passing quarantine owner; or
  - `unrelated_preexisting`: null inventory key, exact signature already frozen by Accepted S11B
    evidence, a passing named non-consumer scope owner, and no S11/accepted-contract/release/index/
    write-safety impact. If S11B has no exact baseline signature, this disposition is unavailable.
- [x] Reject changed signatures, duplicate/missing rows, collection errors without ledger rows,
  failing replacement owners, missing inventory/overlay links, or any accepted-behavior failure.
  Zero failures is valid and produces an empty `failures` list, not a fabricated entry.
- [x] Require the aggregate validator to consume preserved `predecessor-reruns-v1.json`, current
  `predecessor-reruns-v2.json`, `guarded-execution-provenance-v1.json`, and
  `disposable-postgres-target-receipt.json`; cross-bind their command/cwd/UTC/source-hash/JUnit/
  target/cleanup fields to the Accepted receipt and ledger before GREEN.

## Task 6: Reach aggregate evidence GREEN

- [x] Remove only the strict-xfail wrapper after overlay, collected-nodeid, JUnit, and ledger files
  exist. Do not change the validator assertions to fit the evidence.
- [x] Run focused GREEN:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_consumer_acceptance_contract.py::test_s11c_reconciles_all_consumer_evidence_without_legacy_dependency \
  --basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/focused/tmp/pytest \
  --junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11c/focused/junit.xml -q
```

Expected: exactly `1 passed`, no warning/skip/xfail/XPASS.

- [x] After the focused pytest process exits, write a postflight receipt that hashes its JUnit,
  proves exact `1 passed`, and proves Canonical V2 predecessor files plus the exact focused file are
  the complete discovered set with no other exclusion. Focused/postflight files are never fed back
  into the validator. Do not overwrite Task 5 artifacts; a fresh attempt needs a new attempt ID/root.

- [x] Run the same focused owner with tampered temporary copies proving rejection of changed base
  inventory hash, overlay missing/extra entry, unknown disposition, unmatched/changed failure
  signature, duplicate ledger row, missing replacement pass, invented nodeid, and missing Task 11.2
  evidence family. Production and accepted evidence remain untouched.

## Task 7: Run proportional aggregate gates

- [x] Revalidate the immutable exact S11A/S11B rerun receipts and their applicable broad-JUnit
  cross-links after focused GREEN; do not perform a second semantically identical rerun.
- [x] Validate the guarded Admin/predecessor capture receipts plus focused postflight receipt as the
  complete no-external coverage proof. Every failure remains visible in JUnit/ledger; no glob,
  overwrite, or known-failure swallowing is allowed.
- [x] Run static checks:

```bash
cd apps/miroflow-agent
uv run ruff check tests/canonical_v2/test_consumer_acceptance_contract.py
uv run ruff format --check tests/canonical_v2/test_consumer_acceptance_contract.py
uv run python -m py_compile tests/canonical_v2/test_consumer_acceptance_contract.py
```

Expected: all exit `0`.

- [x] Run changed-scope Pyright for the new test. Expected: `0 errors`.
- [x] Run strict/scope/invariant gates:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`; final implementation diff contains only the one new test plus S11C-local
evidence/status artifacts until final acceptance bookkeeping.

- [x] Run the latest Accepted scope, secret, generated-cache, locked-offline package-content,
  source-parity, frozen original PostgreSQL/Milvus/forensic hash, active-pointer, and no-online-write
  checks. Expected: exact invariants retained.
- [x] Obtain one independent implementation/test-integrity review. Repair only S11C test/evidence
  issues. Accepted predecessor or production defects are stop conditions. Require `C=0/I=0`; record
  Minor/YAGNI without another review loop.

## Task 8: Candidate, Accepted, and atomic task closure

- [x] Write `s11c/verification-receipt.json` with exact dependency/contract/plan/test/overlay/ledger/
  JUnit/collected-nodeid hashes, exact predecessor-rerun and broad-JUnit cross-links, focused/postflight
  hashes, disposable-target lifecycle proof, argv/exit codes, safe target identities, inventory
  authority, per-task evidence mapping, protected-source/pointer hashes, and review disposition.
- [x] Mark S11C Candidate only after every required artifact/check exists. Do not change a task at
  Candidate.
- [x] Confirm overlay has zero unresolved base entries, ledger has zero unaccounted or accepted-
  behavior failures, and no accepted path depends on a retired implementation detail.
- [x] With independent `C0/I0`, mark S11C Accepted and atomically change only Tasks 11.1, 11.2, 11.3,
  11.4, and 11.5 from unchecked to checked. Record the exact live ledger before/after with delta
  `+5`; partial closure is forbidden.
- [x] Update only authorized OpenSpec acceptance/change-log/agent-link and existing verification/
  portfolio/convergence pointers needed to reference the Accepted S11C receipt. Do not claim S12,
  user acceptance, production Cutover, or S2C Task 2.8 completion.
- [x] Run strict OpenSpec and `git diff --check` once more. Expected: both exit `0`.

## Rollback checkpoint

Before acceptance, remove only the S11C aggregate test and S11C-local overlay/ledger/JUnit/collected/
receipt evidence; remove the transient database only when its receipt proves this attempt created it
and the exact marker still matches. S11A/B and the accepted inventory remain byte-identical. If accepted evidence is
later invalidated, restore the S11C status/evidence and uncheck Tasks 11.1-11.5 together. No
production, database, index, source, provider, release pointer, Commit, Push, PR, Archive, promotion,
or Cutover rollback is required.
