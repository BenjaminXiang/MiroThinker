# S12A Complete Isolated Candidate Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` only after this plan becomes Ready. Use
> `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. One writer owns
> all S12A production/test/run artifacts. Steps use checkbox syntax for tracking. Do not commit
> before acceptance; after Task `12.1` is Accepted, create exactly one local task commit. Do not Push
> or create a PR.

**Goal:** Build and verify one complete Canonical V2 candidate from exactly accounted accepted
source copies on a fresh disposable PostgreSQL database and fresh isolated index, while retaining
the existing `KnowledgeBuild.build(BuildCandidateRequest) -> CandidateRelease` interface.

**Architecture:** Add one deep isolated `KnowledgeBuild` implementation that owns the full verified
copy → landing → historical assertion policy/authority/gaps → typed projection → durable registry →
full index → physical audit → ephemeral release verification → content receipt/handoff sequence.
Keep local PostgreSQL/filesystem/Milvus Lite behind internal seams and inject only real recorded/
production decision and embedding adapters. The run-local command calls `build` once and emits the
sink-readback Candidate. Production `--serve` fails closed before builder construction until Task
`12.2` supplies its content-addressed serving bundle and live gates; the injected serving seam only
proves later handoff wiring. Neither path contains an active-pointer write or promotion capability.

**Tech Stack:** Python 3.12, Pydantic v2, psycopg 3, PostgreSQL/Alembic, Milvus Lite, existing
Canonical V2 modules, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan reached **Accepted** on `2026-07-23` after the successful fresh r12 build, system tests,
and independent source/safety/evidence review. The user explicitly authorized the exact behavior-
preserving identity-resolution and `DomainProjection` performance prerequisites; their combined
owner matrix reports `87 passed`:

- [x] S10O has an Accepted Slice Contract and matching final receipt SHA-256
      `e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246`.
- [x] S11C has an Accepted aggregate Slice Contract and matching final receipt SHA-256
      `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`; the live ledger is
      `70/80`.
- [x] The live Canonical V2 migration graph has exactly one head and no other writer owns the five
      planned files.
- [x] The accepted S2B source inventory/backup/restore/acceptance hashes still match the executable
      gate and the Accepted original-Milvus identity/original PostgreSQL pause identity remain
      frozen.
- [x] One focused S12A plan/contract re-review reports zero open Critical/Important findings;
      Minor/YAGNI remains nonblocking.
- [x] The newly reviewed Specified artifact hashes, current live ledger, and restored UTC Ready
      timestamp are recorded below.
- [x] Strict OpenSpec validation and `git diff --check` exit `0`.
- [x] Behavior-preserving identity-resolution indexing/streamed hashing and the
      `DomainProjection` assertion-set cache are explicitly authorized, covered by parity and
      large-graph regression evidence, and pass their owner matrix.
- [x] Focused review confirms the prerequisites change no projection behavior, hash, error, schema,
      or public interface.

S2C/Task `2.8` is not a build gate for S12A. Task `12.1` is now checked at `71/80`; aggregate
acceptance remains `49/97`, and Tasks `12.2`-`12.6` remain open. The implementation, source manifest,
r12 isolated database/index/staging, and current envelope evidence remain intentionally uncommitted
and retained because no explicit commit authorization was given.

The superseded first Ready review bound Specified SHA-256 values contract
`33252aa28fe7c765ec371e3824ad9f52295af14931b3d9b783b628d12ece666b`, audit
`4d3fd293621e527b624609e11a0285461e192fceff77849fe4e9ac749f411e72`, and plan
`39ebf4376d99a10e8f919e8ec14c6329f86a73a5051f4067aa6463d60705c24c`. They remain historical
review evidence, not authority for this revision. The focused re-review accepted exact current
Specified hashes contract `3590b70a1a211a34b8ceb34d00d1854536d0d37934ce1443fdb695a282d1f11c`,
audit `ea0f8594fe80dc2248fb9c5fc8e6ec58479526e156e2d140412ff3756033c8ba`, and plan
`03d212c1fe7ca38e1588f4a4713ba998bedbf0885aced75b7cc621bd7f9568e2`. The live ledger is exactly
`70/80` (80 total, 70 complete, 10 open); no task or acceptance checkbox changed.

GREEN evidence before the pause: the source-authority and hostile pre-effect groups passed (`2
passed in 1.30s`); Ruff check/format-check and `git diff --check` passed for the isolated module and
RED owner. The early full graph completed landing, domain/internal/candidate composition, path
eligibility, pure index, registry, typed stores, and embedding. It was stopped
after `9m52s`/about `1.7 GB` in physical-index replay at the repeated
`set(self.assertions)` checks in `domain_projection.py:509,584`. No logical assertion failure was
reported. The hardened mapper later established that the 580 relationship source rows lack
accepted endpoint authority; they now become typed gaps and produce zero relationship projections.
The final r10 graph completed with 1,037 Company projections, 5,561 gaps, and 1,037 physical index
points/documents. Focused builder/runner tests report `67 passed`.

## Minimal file map

- Create `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py`: typed
  50-source manifest, full-table historical mapper, explicit isolated target configuration, deep
  `KnowledgeBuild` implementation, existing-stage composition/replay, durable candidate registry,
  physical audit, exact ephemeral verification, and single-envelope receipt/consumer-handoff sink.
- Create `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py`: public-interface
  RED/GREEN owner over a fresh real PostgreSQL target and fresh Milvus Lite/lookup root, including
  source/gap/failure/safety/cross-wire cases.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/source-build-manifest-v1.json`:
  content-addressed exact disposition for every accepted S2B source plus any explicitly approved
  targeted-recollection staging artifact.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`:
  required-argument composition adapter that calls `build` once, emits the exact sink-readback
  handoff, and fails closed for production serving until Task `12.2`.
- Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`:
  runner RED/GREEN, single-call, handoff, fail-closed production serving, injected
  `0.0.0.0:18188` wiring, one-worker/no-reload, and no-promotion/private-stage owner.

Accepted S12A evidence now exists at
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope-r12.json`;
the earlier untracked `complete-candidate-build-envelope.json` remains historical r6 evidence. Do
not create a migration or modify
`knowledge_build.py`, `contracts.py`, Accepted stage modules/tests, S2/S2B evidence, S10O/S11C
artifacts, original sources, release pointers, or legacy consumers.

## Task 1: Freeze Ready from live predecessors

**Files:**
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/dependency-audit.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s12a-complete-isolated-candidate-builder.md`
- Review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/implementation-plan.md`

- [x] **Step 1: Verify S10O and S11C acceptance from their contracts and receipts**

Read both live contracts, final receipts, and `verification.md` entries. Hash the receipts and ensure
the contracts name the same identities. If either predecessor is not Accepted, leave S12A Specified
and continue that predecessor rather than editing an S12A implementation file.

- [x] **Step 2: Verify live head, ownership, and immutable source gates**

Run from the repository root. These commands inspect only committed control evidence and container
metadata; they never open or hash original Milvus bytes and never connect to PostgreSQL:

```bash
cd apps/miroflow-agent
PYTHONDONTWRITEBYTECODE=1 uv run alembic -c canonical_v2_alembic.ini heads
PYTHONDONTWRITEBYTECODE=1 uv run python \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/backup_restore.py \
  verify-gate \
  --inventory ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-inventory.json \
  --backup-manifest ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/backup-manifest.json \
  --restore-verification ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/restore-verification.json \
  --acceptance-record ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/acceptance-record.json
cd ../..
sha256sum \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-inventory.json \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/backup-manifest.json \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/restore-verification.json \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s2b/acceptance-record.json
apps/miroflow-agent/.venv/bin/python - <<'PY'
import json
from pathlib import Path

inventory = json.loads(
    Path(
        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-inventory.json"
    ).read_text(encoding="utf-8")
)
records = [
    row
    for row in inventory["sources"]
    if row.get("path") == "apps/miroflow-agent/milvus.db"
]
assert records == [
    {
        "access_mode": "hash_only_never_opened",
        "authority": "forensic_source_hash_only",
        "bytes": 1298632704,
        "domains": ["professor", "company", "paper", "patent"],
        "kind": "milvus_lite_original",
        "limitation": (
            "No verified copy exists; client open and collection inspection are forbidden in S2."
        ),
        "path": "apps/miroflow-agent/milvus.db",
        "sha256": "43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc",
    }
]
print(records[0]["sha256"])
PY
docker inspect --format \
  '{{.State.Status}} {{.State.Paused}} {{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}} {{.RW}}{{end}}{{end}}' \
  pgtest
git worktree list --porcelain
git worktree list --porcelain | awk '/^worktree /{print substr($0,10)}' | \
  while IFS= read -r worktree; do
    git -C "$worktree" status --short --untracked-files=all -- \
      apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py \
      apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py \
      .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/source-build-manifest-v1.json \
      .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py \
      .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
  done
```

Expected: Alembic prints exactly `C2_0011 (canonical_v2) (head)`; the formal S2B gate prints
`state=accepted` and `source_count=50`; all four control-file hashes equal the contract; the
committed inventory, without opening the source path, binds the frozen original-Milvus identity;
Docker metadata prints the paused `pgtest` state and exact source volume identity; every worktree
prints no planned-file status. Also confirm the active agent roster has no other S12A writer.

- [x] **Step 3: Re-run accepted construction owners**

```bash
cd apps/miroflow-agent
uv run pytest -q --tb=short \
  tests/canonical_v2/test_knowledge_build_interface.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  tests/canonical_v2/test_release_publication_interface.py
```

Expected: no fail/error/xfail/XPASS. Record the live count, not a historical count.

- [x] **Step 4: Perform one lean Ready review**

Review exact Task 12.1 ownership, deep-module locality, source disposition authority, gate-before-
read/write, fresh target identity, typed gaps, durable registry replay, physical inventory, exact
verification, one-envelope closure, and no promotion. Repair Critical/Important only. Record
Minor/YAGNI, hash the three artifacts, mark them Ready with one UTC timestamp, then run strict
OpenSpec and diff checks. Do not check any OpenSpec task.

The earlier live evidence remains current: S10O receipt
`e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246`; S11C receipt
`281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`; unique head
`C2_0011`; S2B formal gate `state=accepted/source_count=50`; original PostgreSQL metadata
`paused=true` on volume `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`;
all-worktree writer check empty; owner matrix `71 passed, 2 skipped`; strict OpenSpec and
`git diff --check` exit `0`. The focused re-review of the storage/envelope repair reported zero
findings and restored Ready at `2026-07-22T11:57:23Z`.

## Task 2: Write the exact S12A RED owner

**Files:**
- Create: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_isolated.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`

- [x] **Step 1: Add exact import-first missing-target sentinels**

The build owner imports only `src.data_agents.canonical_v2.knowledge_build_isolated`; the runner
owner imports only the S12A runner target. Normal RED uses strict S12A xfails; forced `--runxfail`
must fail only with exact `_MissingIsolatedKnowledgeBuildModule` or
`_MissingCompleteCandidateRunner` sentinels. Each module import occurs before fixture lookup or any
PostgreSQL, filesystem, Milvus, Uvicorn, provider, or port setup, so environment skips cannot hide
RED.

- [x] **Step 2: Add six observable build-interface groups**

Use `KnowledgeBuild.build` as the test surface. Add exactly these groups:

1. `test_source_manifest_accounts_for_every_accepted_source_without_using_requirements_as_facts`;
2. `test_complete_build_uses_verified_copies_landing_authority_projections_registry_index_and_verify`;
3. `test_unrecoverable_or_quarantined_input_records_typed_gap_without_placeholder_fact`;
4. `test_tampered_unapproved_original_symlink_and_crosswired_targets_fail_before_next_effect`;
5. `test_failed_candidate_is_inspectable_retryable_and_never_changes_active_release`;
6. `test_store_replay_and_single_envelope_readback_are_exact_and_conflicts_fail`.

The happy path provisions a fresh explicitly marked disposable database, migrates it to the live
head, creates a fresh marked candidate index root, and uses recorded decision/embedding adapters.
Assert one returned `CandidateRelease`, exact landing streams, four public plus three internal
projection owners, relationship and eligibility hashes, immutable release/build rows, full physical
point/document enumeration, accepted zero-deviation `ReleaseVerification`, valid envelope plus
receipt/handoff hashes, exact nested internal-reference/path-eligibility typed payloads, and
unchanged/absent `publish.active_release`.

The failure groups snapshot landing/knowledge/domain/publish/ops row identities, index files, active
pointer, the Accepted original-Milvus identity record, and adapter calls. They never open or rehash
original Milvus bytes. Each invalid input must stop before the next named effect. Partial parser
data remains evidence; no placeholder parent/object/relation/point is present.

Accepted RED evidence at `2026-07-22`: the build owner contains six executable import-first groups;
normal mode reports exactly `6 xfailed`, and forced `--runxfail` reports exactly six
`_MissingIsolatedKnowledgeBuildModule` failures. Focused spec review reports
`Critical=0 / Important=0`; focused test-quality review is Approved with no open Critical/Important.
The runner RED remains pending Step 3 and is not included in this checkpoint.

- [x] **Step 3: Add two observable runner groups**

Use only `main(args)` plus recording builder/sink/Uvicorn/S11 factory adapters:

7. `test_runner_calls_build_once_and_consumes_exact_sink_handoff_without_private_stage_rebuild`;
8. `test_runner_serves_app_object_on_fixed_host_port_without_promotion_pointer_reload_or_second_build`.

The first group proves exact required arguments, one factory call, one `build` call, candidate/
receipt/handoff equality, and zero private-stage import/call. The second proves the injected
`--serve --host 0.0.0.0 --port 18188` app-object seam, one worker/no reload, and no second build,
promotion, rollback, pointer write, or cleanup. A separate owner proves production serving fails
closed during dependency preflight before builder construction until Task `12.2` supplies its
content-addressed bundle.

- [x] **Step 4: Record normal and forced RED**

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

- [x] **Step 1: Define the typed source/target/receipt models**

Define frozen Pydantic models with canonical JSON hashes:

```python
class SourceDisposition(str, Enum):
    evidence_input = "evidence_input"
    requirements_only = "requirements_only"
    acceptance_only = "acceptance_only"
    protection_only = "protection_only"
    registered_unprojected = "registered_unprojected"
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

class CandidateStagingMarker(ContractModel):
    schema_version: Literal["canonical-v2-candidate-staging-marker-v1"]
    run_id: NonEmptyStr
    candidate_release_id: NonEmptyStr
    source_manifest_sha256: Sha256

class CandidateStagingTarget(ContractModel):
    root: Path
    marker: CandidateStagingMarker

class CompleteCandidateTargetConfig(ContractModel):
    database: DestructiveDatabaseTarget
    index: IsolatedIndexTarget
    staging: CandidateStagingTarget

class CompleteCandidateConsumerHandoff(ContractModel):
    schema_version: Literal["canonical-v2-complete-candidate-handoff-v1"]
    candidate: CandidateRelease
    release_bundle: IsolatedReleaseBundle
    index_projection_request: IndexProjectionRequest
    institution_catalog: InstitutionCatalog
    release_verification: ReleaseVerification
    content_sha256: Sha256

class CompleteCandidateBuildReceipt(ContractModel):
    schema_version: Literal["canonical-v2-complete-candidate-receipt-v1"]
    candidate: CandidateRelease
    consumer_handoff_sha256: Sha256
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
    accepted_original_milvus_record_sha256: Sha256
    accepted_original_milvus_sha256: Sha256
    built_at: CanonicalDatetime
    content_sha256: Sha256

class CompleteCandidateBuildEnvelope(ContractModel):
    schema_version: Literal["canonical-v2-complete-candidate-envelope-v1"]
    receipt: CompleteCandidateBuildReceipt
    consumer_handoff: CompleteCandidateConsumerHandoff
    content_sha256: Sha256
```

Validators enforce exact 50-source accepted-gate coverage in `inventory_entries`,
disposition-specific member fields, unique source/member/batch IDs across both collections, exact
request version/batch agreement, allowed roots, explicit approval for every recollection entry, and
a hash over the complete model excluding only `content_sha256`. `requirements_only`,
`acceptance_only`, `protection_only`, and `registered_unprojected` require no readable content
member and can never reach landing; `evidence_input` requires exact accepted-copy members;
`unrecoverable` requires a typed gap identity. The implementation reuses the Accepted
`DestructiveDatabaseTarget` and `IsolatedIndexTarget` models, adds only the staging marker/target
above, and privately validates that all three targets are absolute, marked, mutually distinct,
non-symlink, non-network, release-bound, and fresh before any input read or write.

- [x] **Step 2: Add one explicit composition factory and private implementation**

The package-internal factory requires an Accepted `DestructiveDatabaseTarget`, an Accepted
`IsolatedIndexTarget`, the typed `CandidateStagingTarget`, backup-gate root, source-manifest path,
recorded/production decision and embedding adapters, clock, and one atomic envelope sink. It
ignores generic environment variables and returns a `KnowledgeBuild` instance. The concrete class
subclasses `KnowledgeBuild` and exposes no public stage methods.

- [x] **Step 3: Implement verified source staging and landing**

Validate the complete manifest and all target identities before opening input bytes. For every
`evidence_input`, copy only from an accepted restore or approved recollection staging path to a fresh
candidate-owned path, reject symlink/protected/hard-link hazards, read/hash the staged bytes once,
and call the accepted PostgreSQL `EvidenceLanding.ingest`. Stream back the exact committed records.
Route requirements/acceptance entries away from landing and retain each `unrecoverable` entry as a
typed gap draft. Persist those drafts only after the candidate registry exists, so no fake prior
release or dangling gap lineage is required.

- [x] **Step 4: Construct and replay authority plus projections**

The production authority adapter converts landing streams through the Accepted assertion/decision,
identity, domain, internal-reference, relationship, and path-eligibility modules. Recorded adapters
may decide ambiguous cases but cannot create evidence. Replay returned request/result pairs through
their public owners and reject release/run/as-of/evidence/hash/scope disagreement. Preserve exactly
four public domains and three internal auxiliary owners; Product capability remains answer-scoped.

- [x] **Step 5: Build the immutable candidate and persist the registry**

Use an ephemeral `IndexProjectionBuilder` to derive the full expected index manifests, then pass the
complete materialization through the existing ephemeral `KnowledgeBuild` so manifest/candidate
construction stays single-owned. Atomically insert the candidate release/build manifest/manifest
sections; persist identity, decision, domain, and relationship results through their Accepted
Postgres adapters; and persist typed gap drafts through Accepted S10O. No Accepted PostgreSQL store
exists for internal-reference or path-eligibility results, so persist only their complete hashes as
manifest sections and retain their exact typed payloads through the final handoff's nested
`IndexProjectionRequest`. Do not add a migration or encode them in
unrelated columns. Read back the complete registry hash. Store-level equal replay within the same
build returns the same content; a conflicting identity or partial write raises and leaves an
inspectable non-active candidate. A second top-level build against any used target is rejected by
the freshness gate.

- [x] **Step 6: Build, audit, verify, and emit the receipt**

Run the accepted isolated index builder in `full` mode on a fresh marked root. Independently enumerate
physical lookup and Milvus contents with the accepted audit, compare exact expected/actual points and
manifests, and call `ReleasePublication.verify` only. Require accepted exact parity and zero missing/
extra/stale/cross-release points. Re-read database registry and active-pointer state; construct the
exact five-artifact `CompleteCandidateConsumerHandoff`; bind its hash in the receipt; contain both
typed values in one `CompleteCandidateBuildEnvelope`; validate all three hashes; then write and
fsync one temporary envelope, publish it by same-filesystem no-overwrite hard link, fsync the
directory, and read back that same file. Return
the exact handoff candidate only after envelope readback and cross-binding succeed. Never call
`promote` or `rollback`.

- [x] **Step 7: Reach focused GREEN**

Run only `tests/canonical_v2/test_knowledge_build_isolated.py`. Expected: exactly six build groups
pass with no xfail/XPASS and no external network. The two runner groups remain exact missing-runner
RED until Task 4 implements the runner.

## Task 4: Freeze the real source-build manifest and run adapter

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/source-build-manifest-v1.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`

- [x] **Step 1: Generate and independently validate the manifest**

Account for every exact S2B source ID in `inventory_entries`. Bind evidence inputs to all admitted
verified restore members; classify PRDs/specs/tests/corpora as requirements/acceptance only; name
exact typed gaps for unrecoverable bytes. Put approved targeted recollection in its separate
collection only when an approval reference and immutable staging-member hash exist. Sort entries and
members by identity and compute the canonical content hash. Compare source IDs, member identities,
and gate hashes mechanically to the accepted S2/S2B documents.

- [x] **Step 2: Implement the runner as a pure composition adapter**

Require explicit CLI values for database URL, expected database, target kind `disposable`, backup
gate root, source manifest, candidate staging root, index root/marker, release ID, run ID, recorded
decision/embedding bundles, one envelope output, and the Accepted frozen original-Milvus identity
record. Reject missing,
conflicting, relative, generic-env, original, nonfresh, or cross-release values before constructing
the builder. Call `KnowledgeBuild.build` exactly once, verify envelope readback, print secret-free
candidate/receipt/handoff identities, and exit. Do not import stage implementations other than the
isolated composition factory and shared request model; expose no promote/rollback/cutover flag.

- [x] **Step 3: Test runner locality and safety**

The run-local owner invokes `main(args)` with recording adapters and asserts required arguments,
generic-environment independence, one factory call, one `build` call, exact request construction,
no-overwrite one-file envelope output, sanitized output/errors, and no stage/promotion call. A malformed
envelope or candidate/receipt/handoff mismatch returns nonzero without printing success.

```bash
uv run pytest -q --tb=short \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
```

Expected: all runner contract cases pass with no external effect.

- [x] **Step 4: Reach complete focused GREEN**

The final combined builder/runner matrix reports `104 passed in 340.20s`, with no external provider or
production resource. The injected serving case is interface-only; production serving fails closed.

## Task 5: Execute one fresh complete isolated candidate

**Files:**
- Generate: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope-r12.json`

- [x] **Step 1: Provision only owned fresh targets**

Create one new explicitly named/marked disposable PostgreSQL database and migrate it through the
live existing head using the accepted explicit-target path. Create one new empty marked isolated
index root and one new candidate staging root. Record identities before the build. Do not reuse S7
acceptance targets or open original sources.

- [x] **Step 2: Run the command with recorded offline adapters**

Invoke `complete_candidate_runner.py` with every required explicit argument. Expected: exit `0`, one
`CandidateRelease`, one accepted zero-deviation verification, and one content-valid envelope. No live
Web/LLM/embedding provider is needed for S12A.

- [x] **Step 3: Independently read back all effects**

Re-run source-manifest coverage, PostgreSQL typed-row/release/manifest counts and hashes, gap
honesty, full candidate-owned lookup/Milvus physical inventory, envelope/receipt/handoff hashes,
active-pointer before/after, Accepted frozen original-Milvus identity-record binding, and original
PostgreSQL pause metadata from independent readers. Never read original Milvus bytes or connect to
original PostgreSQL. Every release and projection must equal the candidate; no active pointer may
change.

r12 completed with release `candidate-s12a-20260723-r12`, run `s12a-build-20260723-r12`, and raw
envelope SHA-256 `a2684f9b9bd42c8727625fa7e057f654c6539a6e97924eccfdfb913fdfef9cbc`.
Independent model, database, and index readers confirm 5,561 landing records, 1,037 Company
projections, zero other domain/relationship projections, 5,561 one-to-one evidence-bound gaps,
1,037 points/documents, zero parity deviations, and no active release. Original `pgtest` remains
paused and original Milvus was not opened. r10/r11 remain stale historical evidence.

## Task 6: Verification, review, and Task 12.1 acceptance

**Files:**
- Update only after Candidate evidence: S12A contract/plan/envelope and existing verification/status
  artifacts allowed by AGENTS.md.

- [x] **Step 1: Run focused and broad tests**

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

Actual: focused builder/runner `104 passed`; exact owner matrix `169 passed, 2 skipped`; complete
no-external Canonical V2 `542 passed, 148 skipped, 3 warnings`; identity/domain prerequisite matrix
`87 passed`. All skips require explicit external target settings; the three warnings are expected
Pydantic serialization warnings from intentional invalid-value tests.

- [x] **Step 2: Run static/package/strict checks**

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

Actual: complete Canonical V2 Ruff and focused format checks pass; Pyright reports zero findings;
`py_compile`, unique head `C2_0011`, accepted S2B gate, strict OpenSpec, diff, scoped secret/cache,
and wheel/source-parity checks pass. The two-step offline lock/build gate produced a 282-entry wheel
with SHA-256 `f3566145f55e2b2fc49172d79818d93e1efd2d0c98cb4e817e621fe8636abe68` and no tests/`.agents`.

- [x] **Step 3: Obtain one merged final review**

Review source authority, no-placeholder behavior, deep interface, durable registry, physical
inventory, exact verification, failure/replay safety, tests, target/frozen-source safety, and task
ownership. Repair Critical/Important only and re-run affected checks. Record Minor/YAGNI without
another theoretical expansion loop.

- [x] **Step 4: Accept only Task 12.1**

When all evidence is current and review has zero open Critical/Important, mark S12A Accepted and
check exactly Task `12.1`. Record a live ledger delta of `+1`. Task `12.3` remains unchecked for
S12B even though the S12A envelope receipt contributes candidate evidence. Task `12.4` may record
pre-run commands but remains unchecked; Task `12.5` awaits explicit user acceptance; Task `12.6` awaits
separate Cutover authorization. Do not Push, create a PR, promote, archive, or clean up original/
forensic resources.

Actual: final source and safety reviews plus independent r12 evidence audit report GO with zero
Critical/Important findings. S12A and exactly Task `12.1` are Accepted; the task ledger moved from
`70/80` to `71/80`, while acceptance remains `49/97`.

- [ ] **Step 5: Create the one local Accepted-task commit**

Stage only the S12A implementation/test/run artifacts, this contract/audit/plan, the exact Task
`12.1` status/evidence updates, and no unrelated path. Create one local commit with message
`feat(canonical-v2): build isolated S12A candidate`, then require `git status --short --branch` to
show a clean worktree. Do not push it.

Not run: repository policy requires the user to explicitly request a commit. The current broad
implementation instruction does not grant commit authority, so the Accepted checkpoint remains
intentionally uncommitted.

## Rollback note

Before acceptance, remove only the five S12A files and S12A-owned generated envelope; drop/remove
only explicitly named S12A-owned disposable database, staging, and index resources. After acceptance,
also restore exactly Task `12.1` and its status/evidence entries. Never rewrite a migration, delete
nonempty durable evidence, remove shared predecessor artifacts, open original Milvus, start original
PostgreSQL, or move a release/index pointer.
