# S12A Complete Isolated Candidate Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` only after this plan becomes Ready. Use
> `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. One writer owns
> all S12A production/test/run artifacts. Steps use checkbox syntax for tracking. Do not Commit.

**Goal:** Build and verify one complete Canonical V2 candidate from exactly accounted accepted
source copies on a fresh disposable PostgreSQL database and fresh isolated index, while retaining
the existing `KnowledgeBuild.build(BuildCandidateRequest) -> CandidateRelease` interface.

**Architecture:** Add one deep isolated `KnowledgeBuild` implementation that owns the full verified
copy → landing → historical assertion policy/authority/gaps → typed projection → durable registry →
full index → physical audit → ephemeral release verification → content receipt/handoff sequence.
Keep local PostgreSQL/filesystem/Milvus Lite behind internal seams and inject only real recorded/
production decision and embedding adapters. The run-local command calls `build` once and may serve
the sink-readback candidate through existing S11 factories at `0.0.0.0:18188`; it contains no build
stage logic, active-pointer write, or promotion capability.

**Tech Stack:** Python 3.12, Pydantic v2, psycopg 3, PostgreSQL/Alembic, Milvus Lite, existing
Canonical V2 modules, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan is **reviewable Specified** after the `C3/I4` contract repair at
`2026-07-21T19:24:16Z`. It is not Ready. Do not execute Task 2 or later until:

- [x] S10O has an Accepted Slice Contract and matching final receipt SHA-256
      `e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246`.
- [x] S11C has an Accepted aggregate Slice Contract and matching final receipt SHA-256
      `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`; the live ledger is
      `70/80`.
- [ ] The live Canonical V2 migration graph has exactly one head and no other writer owns the five
      planned files.
- [ ] The accepted S2B source inventory/backup/restore/acceptance hashes still match the executable
      gate and the original Milvus hash/original PostgreSQL pause identity remain frozen.
- [ ] One lean S12A plan/contract review reports zero open Critical/Important findings; Minor/YAGNI
      remains nonblocking.
- [ ] The Specified artifact hashes, current live ledger, and UTC Ready timestamp are recorded.
- [ ] Strict OpenSpec validation and `git diff --check` exit `0`.

S2C/Task `2.8` is not a Ready gate for S12A. No OpenSpec task checkbox, production code, test,
source-build manifest, database, index, or receipt may be created while this plan remains Specified.

The preceding audit's `C3/I4` findings are repaired in this plan, contract, and dependency audit;
open Critical/Important is `0` pending the independent Ready review. This repair did not change an
OpenSpec task or waive any remaining gate.

## Minimal file map

- Create `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`: typed
  50-source manifest, full-table historical mapper, explicit isolated target configuration, deep
  `KnowledgeBuild` implementation, existing-stage composition/replay, durable candidate registry,
  physical audit, exact ephemeral verification, and receipt/consumer-handoff sink.
- Create `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py`: public-interface
  RED/GREEN owner over a fresh real PostgreSQL target and fresh Milvus Lite/lookup root, including
  source/gap/failure/safety/cross-wire cases.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/source-build-manifest-v1.json`:
  content-addressed exact disposition for every accepted S2B source plus any explicitly approved
  targeted-recollection staging artifact.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`:
  required-argument composition adapter that calls `build` once and optionally serves the exact
  sink-readback handoff through the existing S11 app factories.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`:
  import-first runner RED/GREEN, single-call, handoff, `0.0.0.0:18188`, one-worker/no-reload, and
  no-promotion/private-stage owner.

After Candidate evidence exists, generate
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-receipt.json` and
the normal S12A status/verification updates. Do not create a migration or modify
`knowledge_build.py`, `contracts.py`, Accepted stage modules/tests, S2/S2B evidence, S10O/S11C
artifacts, original sources, release pointers, or legacy consumers.

## Task 1: Freeze Ready from live predecessors

**Files:**
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/dependency-audit.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s12a-complete-isolated-candidate-builder.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/implementation-plan.md`

- [ ] **Step 1: Verify S10O and S11C acceptance from their contracts and receipts**

Read both live contracts, final receipts, and `verification.md` entries. Hash the receipts and ensure
the contracts name the same identities. If either predecessor is not Accepted, leave S12A Specified
and continue that predecessor rather than editing an S12A implementation file.

- [ ] **Step 2: Verify live head, ownership, and immutable source gates**

Run from the repository root:

```bash
rg -n "^revision:|^down_revision:" \
  apps/miroflow-agent/canonical_v2_alembic/versions/*.py
git status --short -- \
  apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py \
  apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a
sha256sum apps/miroflow-agent/milvus.db
```

Expected: one migration head; no concurrent writer on planned files; original Milvus SHA-256 equals
the frozen verification-contract value. Confirm original `pgtest` remains paused without starting or
connecting to it.

- [ ] **Step 3: Re-run accepted construction owners**

```bash
cd apps/miroflow-agent
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_build_interface.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  tests/canonical_v2/test_release_publication_interface.py
```

Expected: no fail/error/xfail/XPASS. Record the live count, not a historical count.

- [ ] **Step 4: Perform one lean Ready review**

Review exact Task 12.1 ownership, deep-module locality, source disposition authority, gate-before-
read/write, fresh target identity, typed gaps, durable registry replay, physical inventory, exact
verification, receipt closure, and no promotion. Repair Critical/Important only. Record Minor/YAGNI,
hash the three artifacts, mark them Ready with one UTC timestamp, then run strict OpenSpec and diff
checks. Do not check any OpenSpec task.

## Task 2: Write the exact S12A RED owner

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`

- [ ] **Step 1: Add exact import-first missing-target sentinels**

The build owner imports only `src.data_agents.canonical_v2.knowledge_build_isolated`; the runner
owner imports only the S12A runner target. Normal RED uses strict S12A xfails; forced `--runxfail`
must fail only with exact `_MissingIsolatedKnowledgeBuildModule` or
`_MissingCompleteCandidateRunner` sentinels. Each module import occurs before fixture lookup or any
PostgreSQL, filesystem, Milvus, Uvicorn, provider, or port setup, so environment skips cannot hide
RED.

- [ ] **Step 2: Add six observable build-interface groups**

Use `KnowledgeBuild.build` as the test surface. Add exactly these groups:

1. `test_source_manifest_accounts_for_every_accepted_source_without_using_requirements_as_facts`;
2. `test_complete_build_uses_verified_copies_landing_authority_projections_registry_index_and_verify`;
3. `test_unrecoverable_or_quarantined_input_records_typed_gap_without_placeholder_fact`;
4. `test_tampered_unapproved_original_symlink_and_crosswired_targets_fail_before_next_effect`;
5. `test_failed_candidate_is_inspectable_retryable_and_never_changes_active_release`;
6. `test_exact_replay_is_idempotent_and_same_identity_different_content_fails`.

The happy path provisions a fresh explicitly marked disposable database, migrates it to the live
head, creates a fresh marked candidate index root, and uses recorded decision/embedding adapters.
Assert one returned `CandidateRelease`, exact landing streams, four public plus three internal
projection owners, relationship and eligibility hashes, immutable release/build rows, full physical
point/document enumeration, accepted zero-deviation `ReleaseVerification`, a valid receipt hash,
and unchanged/absent `publish.active_release`.

The failure groups snapshot landing/knowledge/domain/publish/ops row identities, index files, active
pointer, original Milvus hash, and adapter calls. Each invalid input must stop before the next named
effect. Partial parser data remains evidence; no placeholder parent/object/relation/point is present.

- [ ] **Step 3: Add two observable runner groups**

Use only `main(args)` plus recording builder/sink/Uvicorn/S11 factory adapters:

7. `test_runner_calls_build_once_and_consumes_exact_sink_handoff_without_private_stage_rebuild`;
8. `test_runner_serves_app_object_on_fixed_host_port_without_promotion_pointer_reload_or_second_build`.

The first group proves exact required arguments, one factory call, one `build` call, candidate/
receipt/handoff equality, and zero private-stage import/call. The second passes
`--serve --host 0.0.0.0 --port 18188`, verifies the exact five-artifact handoff, a run-local-only
`PublishedRelease` view, existing S11 planner/read/runtime/app factories, recorded proposal/answer/
Web adapters, `uvicorn.run(app_object, workers=1, reload=False)`, and no import string, startup build,
promotion, rollback, pointer write, or cleanup.

- [ ] **Step 4: Record normal and forced RED**

```bash
cd apps/miroflow-agent
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_build_isolated.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
uv run pytest -q --tb=short --runxfail \
  tests/canonical_v2/test_knowledge_build_isolated.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
```

Expected before implementation: exactly eight strict S12A xfails in normal mode; forced mode reports
exactly eight failures for the exact missing targets. No target, port, database, index, provider, or
server work occurs.

## Task 3: Implement the source manifest and deep build module

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`

- [ ] **Step 1: Define the typed source/target/receipt models**

Define frozen Pydantic models with canonical JSON hashes:

```python
class SourceDisposition(str, Enum):
    evidence_input = "evidence_input"
    requirements_only = "requirements_only"
    acceptance_only = "acceptance_only"
    unrecoverable = "unrecoverable"

class SourceBuildMember(ContractModel):
    member_id: NonEmptyStr
    source_batch_id: NonEmptyStr
    source_kind: NonEmptyStr
    content_path: Path
    byte_size: int
    content_sha256: Sha256
    parser: ParserReference
    observed_at: CanonicalDatetime
    parent_source_id: NonEmptyStr

class SourceBuildEntry(ContractModel):
    source_id: NonEmptyStr
    disposition: SourceDisposition
    source_family: NonEmptyStr
    members: tuple[SourceBuildMember, ...]
    approval_reference: NonEmptyStr | None
    gap_id: NonEmptyStr | None
    rationale: NonEmptyStr

class SourceBuildManifest(ContractModel):
    schema_version: Literal["canonical-v2-source-build-manifest-v1"]
    source_inventory_sha256: Sha256
    backup_manifest_sha256: Sha256
    restore_verification_sha256: Sha256
    acceptance_record_sha256: Sha256
    restore_root: Path
    approved_recollection_root: Path | None
    inventory_entries: tuple[SourceBuildEntry, ...]
    targeted_recollection_entries: tuple[SourceBuildEntry, ...] = ()
    content_sha256: Sha256

class CompleteCandidateBuildReceipt(ContractModel):
    schema_version: Literal["canonical-v2-complete-candidate-receipt-v1"]
    candidate: CandidateRelease
    source_manifest_sha256: Sha256
    gate_hashes: dict[NonEmptyStr, Sha256]
    landing_receipt_hashes: tuple[Sha256, ...]
    gap_hashes: tuple[Sha256, ...]
    authority_sha256: Sha256
    candidate_projection_sha256: Sha256
    relationship_projection_sha256: Sha256
    database_registry_sha256: Sha256
    index_result_sha256: Sha256
    physical_index_snapshot_sha256: Sha256
    release_verification: ReleaseVerification
    active_release_before_sha256: Sha256
    active_release_after_sha256: Sha256
    original_milvus_sha256: Sha256
    built_at: CanonicalDatetime
    content_sha256: Sha256
```

Validators enforce exact 50-source accepted-gate coverage in `inventory_entries`,
disposition-specific member fields, unique source/member/batch IDs across both collections, exact
request version/batch agreement, allowed roots, explicit approval for every recollection entry, and
a hash over the complete model excluding only `content_sha256`.

- [ ] **Step 2: Add one explicit composition factory and private implementation**

The package-internal factory requires explicit database URL/identity/kind, backup-gate root,
source-manifest path, candidate staging root, isolated index target, recorded/production decision and
embedding adapters, clock, and receipt sink. It ignores generic environment variables and returns a
`KnowledgeBuild` instance. The concrete class subclasses `KnowledgeBuild` and exposes no public
stage methods.

- [ ] **Step 3: Implement verified source staging and landing**

Validate the complete manifest and all target identities before opening input bytes. For every
`evidence_input`, copy only from an accepted restore or approved recollection staging path to a fresh
candidate-owned path, reject symlink/protected/hard-link hazards, read/hash the staged bytes once,
and call the accepted PostgreSQL `EvidenceLanding.ingest`. Stream back the exact committed records.
Route requirements/acceptance entries away from landing and retain each `unrecoverable` entry as a
typed gap draft. Persist those drafts only after the candidate registry exists, so no fake prior
release or dangling gap lineage is required.

- [ ] **Step 4: Construct and replay authority plus projections**

The production authority adapter converts landing streams through the Accepted assertion/decision,
identity, domain, internal-reference, relationship, and path-eligibility modules. Recorded adapters
may decide ambiguous cases but cannot create evidence. Replay returned request/result pairs through
their public owners and reject release/run/as-of/evidence/hash/scope disagreement. Preserve exactly
four public domains and three internal auxiliary owners; Product capability remains answer-scoped.

- [ ] **Step 5: Build the immutable candidate and persist the registry**

Use an ephemeral `IndexProjectionBuilder` to derive the full expected index manifests, then pass the
complete materialization through the existing ephemeral `KnowledgeBuild` so manifest/candidate
construction stays single-owned. Atomically insert the candidate release/build manifest/manifest
sections, persist typed stage results through Accepted Postgres adapters, persist the typed gap
drafts through Accepted S10O, and read back the complete registry hash. Equal replay returns the
same content; collision or partial write raises and leaves an inspectable non-active candidate.

- [ ] **Step 6: Build, audit, verify, and emit the receipt**

Run the accepted isolated index builder in `full` mode on a fresh marked root. Independently enumerate
physical lookup and Milvus contents with the accepted audit, compare exact expected/actual points and
manifests, and call `ReleasePublication.verify` only. Require accepted exact parity and zero missing/
extra/stale/cross-release points. Re-read database registry and active-pointer state, construct the
complete receipt, validate its content hash, then write it atomically through the injected sink.
Return the `CandidateRelease` only after receipt readback succeeds. Never call `promote` or
`rollback`.

- [ ] **Step 7: Reach focused GREEN**

Run the Task 2 commands. Expected: all six groups pass with no xfail/XPASS and no external network.

## Task 4: Freeze the real source-build manifest and run adapter

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/source-build-manifest-v1.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`

- [ ] **Step 1: Generate and independently validate the manifest**

Account for every exact S2B source ID in `inventory_entries`. Bind evidence inputs to all admitted
verified restore members; classify PRDs/specs/tests/corpora as requirements/acceptance only; name
exact typed gaps for unrecoverable bytes. Put approved targeted recollection in its separate
collection only when an approval reference and immutable staging-member hash exist. Sort entries and
members by identity and compute the canonical content hash. Compare source IDs, member identities,
and gate hashes mechanically to the accepted S2/S2B documents.

- [ ] **Step 2: Implement the runner as a pure composition adapter**

Require explicit CLI values for database URL, expected database, target kind `disposable`, backup
gate root, source manifest, candidate staging root, index root/marker, release ID, run ID, recorded
decision/embedding bundles, receipt output, and frozen original-Milvus hash. Reject missing,
conflicting, relative, generic-env, original, nonfresh, or cross-release values before constructing
the builder. Call `KnowledgeBuild.build` exactly once, verify receipt readback, print secret-free
candidate/receipt identities, and exit. Do not import stage implementations other than the isolated
composition factory and shared request model; expose no promote/rollback/cutover flag.

- [ ] **Step 3: Test runner locality and safety**

The run-local owner invokes `main(args)` with recording adapters and asserts required arguments,
generic-environment independence, one factory call, one `build` call, exact request construction,
atomic receipt output, sanitized output/errors, and no stage/promotion call. A malformed receipt or
candidate/receipt mismatch returns nonzero without printing success.

```bash
uv run pytest -q --tb=short \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
```

Expected: all runner contract cases pass with no external effect.

## Task 5: Execute one fresh complete isolated candidate

**Files:**
- Generate: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-receipt.json`

- [ ] **Step 1: Provision only owned fresh targets**

Create one new explicitly named/marked disposable PostgreSQL database and migrate it through the
live existing head using the accepted explicit-target path. Create one new empty marked isolated
index root and one new candidate staging root. Record identities before the build. Do not reuse S7
acceptance targets or open original sources.

- [ ] **Step 2: Run the command with recorded offline adapters**

Invoke `complete_candidate_runner.py` with every required explicit argument. Expected: exit `0`, one
`CandidateRelease`, one accepted zero-deviation verification, and one content-valid receipt. No live
Web/LLM/embedding provider is needed for S12A.

- [ ] **Step 3: Independently read back all effects**

Re-run source-manifest coverage, PostgreSQL typed-row/release/manifest counts and hashes, gap
honesty, full lookup/Milvus physical inventory, receipt hash, active-pointer before/after, frozen
original Milvus hash, and original PostgreSQL pause checks from independent readers. Every release
and projection must equal the candidate; no active pointer may change.

## Task 6: Verification, review, and Task 12.1 acceptance

**Files:**
- Update only after Candidate evidence: S12A contract/plan/receipt and existing verification/status
  artifacts allowed by AGENTS.md.

- [ ] **Step 1: Run focused and broad tests**

```bash
cd apps/miroflow-agent
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_build_interface.py \
  tests/canonical_v2/test_knowledge_build_isolated.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  tests/canonical_v2/test_release_publication_interface.py
uv run pytest -q --tb=short -m "not requires_api_key and not integration and not slow" \
  tests/canonical_v2
```

Expected: no fail/error/xfail/XPASS in the owner matrix and no unexpected failure in the complete
no-external suite. Record live counts.

- [ ] **Step 2: Run static/package/strict checks**

```bash
uv run ruff check \
  src/data_agents/canonical_v2/knowledge_build_isolated.py \
  tests/canonical_v2/test_knowledge_build_isolated.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
uv run ruff format --check \
  src/data_agents/canonical_v2/knowledge_build_isolated.py \
  tests/canonical_v2/test_knowledge_build_isolated.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
uv run pyright src/data_agents/canonical_v2 tests/canonical_v2
cd ../..
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Also build a fresh locked-offline wheel, confirm inclusion/source parity for
`knowledge_build_isolated.py`, exclude tests/`.agents`, run high-confidence secret/generated-cache
checks, and remove only generated outputs owned by this run.

- [ ] **Step 3: Obtain one merged final review**

Review source authority, no-placeholder behavior, deep interface, durable registry, physical
inventory, exact verification, failure/replay safety, tests, target/frozen-source safety, and task
ownership. Repair Critical/Important only and re-run affected checks. Record Minor/YAGNI without
another theoretical expansion loop.

- [ ] **Step 4: Accept only Task 12.1**

When all evidence is current and review has zero open Critical/Important, mark S12A Accepted and
check exactly Task `12.1`. Record a live ledger delta of `+1`. Task `12.3` remains unchecked for
S12B even though the S12A receipt contributes candidate evidence. Task `12.4` may record pre-run
commands but remains unchecked; Task `12.5` awaits explicit user acceptance; Task `12.6` awaits
separate Cutover authorization. Do not Commit, Push, PR, promote, archive, or clean up original/
forensic resources.

## Rollback note

Before acceptance, remove only the five S12A files and S12A-owned generated receipt; drop/remove
only explicitly named S12A-owned disposable database, staging, and index resources. After acceptance,
also restore exactly Task `12.1` and its status/evidence entries. Never rewrite a migration, delete
nonempty durable evidence, remove shared predecessor artifacts, open original Milvus, start original
PostgreSQL, or move a release/index pointer.
