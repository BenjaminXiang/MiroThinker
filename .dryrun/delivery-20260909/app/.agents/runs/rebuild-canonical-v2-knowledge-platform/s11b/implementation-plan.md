# S11B Canonical V2 Consumer Migration and Legacy Quarantine Implementation Plan

> **For agentic workers:** S11B is Accepted; do not reopen or rerun this plan. The historical
> execution used `superpowers:subagent-driven-development`, test-driven RED/GREEN, and
> verification-before-completion with one consumer-boundary writer. S11C owns the next aggregate
> acceptance work. Do not Commit.

**Goal:** Make the candidate admin application, offline evidence writer, and smoke retrieval caller
consume only accepted Canonical V2 release/read/landing/gap interfaces while quarantining every
registered V042/direct-SQL/fixed-handler/direct-index path.

**Architecture:** Install one explicit release-bound admin runtime beside Accepted S11A/S10O. The
candidate app imports only S11A's V2-only chat/contracts/dependency seam, serves typed projections
and gaps through the built-in `browse.html`, records feedback from the immutable server-retained V2
checkpoint, and performs no canonical/index mutation. Add one gate-before-read explicit-target
EvidenceLanding CLI and one black-box `/api/chat` smoke caller; a versioned inventory plus
route/import guards makes all old writer/retrieval/index/React entry points reference-only.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Canonical V2 typed projection/read/landing/gap
contracts, built-in HTML/JavaScript, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan is **Accepted** at `2026-07-21T12:54:16Z` after the final receipt/state review reported
`Critical=0` and `Important=0`. Fresh signature-v3 row
`a9bdfcdb5d2b8a6409811de6bf8c53bc66e7e2d78afa92edb9cc09cf0b06f668` records Canonical V2 `530`
tests at exit `0` and Admin `596` tests at exit `1` with 18 failures plus 4 setup errors retained for
S11C, 15 attributable blocked attempts, zero forbidden attempts, complete cleanup, exact per-run
temp roots, and 22/22 independently replayable persisted-JUnit signatures. The earlier v2 Candidate
attempt was rejected and deleted. The ledger remains `65/80`; Tasks `11.1`-`11.5` and acceptance
remain unchanged.

- [x] The S10O Slice Contract and final verification receipt both say Accepted.
- [x] The historical S11A Slice Contract/receipt and successor S9J Slice Contract/receipt all say
  Accepted. Historical S11A hashes remain immutable; S9J explicitly owns the corrected live bytes.
- [x] One lean S11B audit/plan/contract review reports zero open Critical/Important findings.
- [x] The review freezes V2-only import quarantine, typed read-only feedback checkpoint use,
  the aggregate app-state gap seam, verified `IsolatedReleaseBundle` composition, production
  SupplementalBudget/EnumerationPolicy binding, S2B restore-member-only ingest, exact admin
  allowlists/bounds, canonical inventory bytes, deterministic guarded baseline production, static
  export ordering, the preserved zero-arg S10O dependency plus exact candidate override, replayed
  four-artifact graph integrity, opaque-port effect ordering, unknown-API `404`, exact candidate route/static/framework-doc policy,
  inventory/S11C receipt fields, the complete Python-and-shell discovery universe, and the
  built-in-UI/legacy-React boundary.
- [x] Minor/YAGNI findings are recorded as non-blocking without another theoretical review loop.
- [x] Strict OpenSpec validation exits `0`.
- [x] Reviewed current In Progress dependency hashes and a UTC timestamp are recorded before the
  focused GREEN/broad-baseline Candidate gate.

S2C is not a Candidate gate for deterministic consumer wiring. S12 owns complete candidate construction
and installation. No Commit, Push, PR, Archive, promotion, production-like Cutover, original-source
write, or destructive legacy cleanup belongs to this plan.

## File map

### Admin backend and minimal built-in candidate surface

- Create `apps/admin-console/backend/services/canonical_v2_admin.py`: one release-bound read/admin
  facade and aggregate consumer composition over a verified release bundle, exact typed
  projections, relationship/read authority, and Accepted S10O operations.
- Create `apps/admin-console/backend/api/canonical_v2_consumers.py`: bounded status, four-domain
  list/detail/facet/related/export endpoints over that facade.
- Modify `apps/admin-console/backend/canonical_v2_deps.py`: resolve only explicitly installed S11A,
  S10O, and S11B members from one candidate aggregate app-state runtime without importing
  `backend.deps` or using environment fallbacks on candidate requests; preserve the Accepted S10O
  zero-argument getter/composer unchanged and add a distinct request getter for candidate override.
- Modify `apps/admin-console/backend/main.py`: register only health, S11A chat, S10O operations, and
  S11B consumer routers from V2-only modules; stop importing/registering legacy chat/deps/routers,
  React SPA, and seed cron.
- Modify `apps/admin-console/backend/api/canonical_v2_chat.py`: migrate only `/chat/feedback` to a
  server-bound S10O gap; preserve Accepted S11A chat/reset behavior.
- Modify `apps/admin-console/backend/static/browse.html`: use the V2 consumer endpoints or show a
  bounded runtime-unavailable state; remove `/api/data/*` calls and render escaped text only.
- Create `apps/admin-console/tests/test_canonical_v2_consumer_migration.py`: exact route/runtime/
  feedback/quarantine/static-UI and observable admin vertical owner.

`apps/admin-console/frontend/**` is `reference_only`: do not modify, mount, import, test, or build it
for S11B. The candidate UI is `browse.html`; the existing static chat page may retain S11A chat.

### Sanctioned CLI and quarantine boundary

- Create `apps/miroflow-agent/scripts/run_canonical_v2_evidence_ingest.py`: explicit-target one-call
  `EvidenceLanding.ingest` CLI.
- Create `apps/admin-console/scripts/smoke_canonical_v2_candidate.py`: explicit-base/expected-release
  black-box `/api/chat` smoke caller.
- Create `apps/miroflow-agent/src/data_agents/canonical_v2/legacy_consumer_quarantine.py`: load and
  validate the versioned inventory; expose no runtime feature flag or fallback.
- Create `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/legacy-consumer-inventory-v1.json`:
  exhaustive retired-router/module/script mapping to a V2 replacement or `reference_only`.
- Create `apps/miroflow-agent/tests/canonical_v2/test_consumer_migration_boundary.py`: discovered
  entrypoint classification plus candidate-app/CLI import boundary owner.
- Create `apps/miroflow-agent/tests/scripts/test_run_canonical_v2_evidence_ingest.py`: exact target,
  accepted S2B restore-member, hash, receipt, and no-fallback CLI owner.
- Create `apps/admin-console/tests/test_smoke_canonical_v2_candidate.py`: explicit URL/release and V2
  trace smoke owner.
- Create `apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py`: fixed-partition,
  fail-closed no-external baseline producer.
- Create `apps/miroflow-agent/tests/scripts/test_capture_canonical_v2_s11b_baseline.py`: producer
  argv/environment/socket/psycopg/artifact/receipt owner.

### Evidence only after implementation

- Add `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/verification-receipt.json` only
  after Candidate evidence exists.
- Add S11B-local `baseline/collected/*.txt` and `baseline/junit/*.xml` only when the broad baseline
  commands run. The receipt content-binds them; they are evidence for S11C, not test waivers.
- Update only S11B/status/verification pointers after implementation. Do not check any OpenSpec task.

Do not modify Canonical V2 algorithms, migrations, accepted S10O/S11A contracts, old V001-V042
migrations, original sources, index bytes, or release pointers. Retired legacy source files remain
in place until S11C makes the aggregate retention decision.

## Task 1: Confirm dependencies, live inventory, and refresh the Candidate gate

- [x] Read the final S10O, historical S11A, and successor S9J contracts and receipts directly. All
  three are Accepted; the formal ledger remains `65/80`.
- [x] Bind the exact historical Accepted S11A receipt SHA-256
  `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3` and its final service,
  route, dependency, and owner hashes respectively as
  `163691d31a36134df3c6975e820d759fd1734a367ae93e33005f2e8247444644`,
  `b8f6fa7b6c8a3469160a8b1699cd87d4af20ddc2b35d0bbbb5cd075d506c9c48`,
  `5567bdbd5fdc0b0f7181b9ee1a989b027e4991811afb2f79b744821f91cbdac7`, and
  `e91aecf229c19e18f98696e2abced0ab9605191d7d8aa54fe6cfa3e0e74a7ba8`. Never rebaseline those
  historical bytes. Bind Accepted S9J receipt
  `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc` and its corrected live chat
  service/S11A-owner/S11B-owner hashes
  `15385247c9cf780e189651c97d15a9ad91fb6a5f8ef5f201bebcc19bb2814b82`,
  `71e04271b9c6ef867795fba0ca3f9427ef418a8b5f736a952f9594130088a06a`, and
  `21e7a68fe7699fd3a4295f87479f060cb2e05de326cf274d6dc9dbae57437f47` as an explicit successor,
  not an S11A rebaseline.
- [x] Reinspect the live public shapes of:

```text
CandidateProjectionResult / PublicDomainProjection
RelationshipProjectionResult
PublishedRelease / ReleaseVerification / IsolatedReleaseBundle / IndexProjectionRequest / BuildManifest
KnowledgeRead.execute
PostgresKnowledgeGapOperations.list_for_admin/get_for_admin/record
ChatFeedbackCheckpoint / CanonicalV2ChatAdapter.get_feedback_checkpoint
EvidenceLanding.ingest / LandingReceipt
```

- [x] Enumerate the current FastAPI routes and executable scripts from the working tree. Classify
  every registered legacy router, every script importing a legacy canonical writer/retrieval/index
  module, and every direct active-index command in the inventory. Do not use a hand-maintained
  partial list as the test oracle.
- [x] Freeze the Specified script discovery baseline as 140 inputs under the two application
  `scripts/` trees: 116 `.py` plus 24 `.sh`; path-list SHA-256
  `9235ceaf2bade6ae5012dc2db74d7ab5c994ba0151ea7cf40c602bfcdd0aa654`; sorted
  path-plus-raw-file-SHA-256 digest
  `9512e595fc49d9b3b7d2cce789d72b2ea4e8421e1c4e8b5d34de7541bc3569d3`. Candidate discovery must
  account for those paths plus exactly the three new sanctioned Python CLIs, for 143 post-S11B
  inputs. The first digest hashes a UTF-8 compact JSON array of sorted paths; the second hashes a
  UTF-8 compact JSON array of sorted `{"path":...,"sha256":...}` objects with sorted keys.
  Neither digest payload has a trailing LF.
- [x] Freeze the non-blocking React reference baseline as 22 files under
  `apps/admin-console/frontend/src/**`, using a sorted path-plus-raw-file-SHA-256 inventory digest of
  `99abf5922399cd8bf20990934fa251c2a246da300fd4af3af384e6a9478ead77`. Its digest payload uses the
  same compact sorted-object JSON encoding with no trailing LF. Candidate evidence must record the
  identical post-implementation count/digest.
- [x] Freeze the inventory acceptance handoff fields: exact inventory SHA-256, counts by category,
  counts by disposition, and the exact sorted `(top-level category, path/module)` pairs/count for
  `s11c_disposition`. The exact receipt pointer is `/legacy_consumer_inventory/sha256`. The immutable
  base count is not rewritten; S11C cannot close Tasks 11.1-11.5 until its separate overlay covers
  every frozen pair exactly once, has zero unresolved entries, and retired-test disposition is
  recorded.
- [x] Capture the live OpenSpec ledger count and record that S11B will make no ledger change.
- [x] Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`.

- [x] Complete one lean read-only review of the S11B audit/plan/contract. Repair only open Critical/
  Important findings; record Minor/YAGNI as non-blocking.
- [x] Freeze reviewed current hashes and record the refreshed focused-GREEN/Candidate gate. Do not
  change production, tests, `tasks.md`, or `acceptance.md` in this task.

## Task 2: Write and observe the exact consumer-boundary RED

**Tests:**

- `apps/admin-console/tests/test_canonical_v2_consumer_migration.py`
- `apps/miroflow-agent/tests/canonical_v2/test_consumer_migration_boundary.py`

- [x] Add dynamic seam loaders with named `_MissingS11BAdminRuntime` and
  `_MissingS11BLegacyInventory` sentinels. Before constructing a database/runtime, starting
  `TestClient`, or reading an artifact, require:

```text
backend.services.canonical_v2_admin.CanonicalV2AdminRuntime
backend.services.canonical_v2_admin.compose_canonical_v2_consumer_runtime
backend.api.canonical_v2_consumers.router
backend.api.canonical_v2_chat.router
backend.canonical_v2_deps.get_canonical_v2_admin_runtime
backend.canonical_v2_deps.get_canonical_v2_gap_operations
backend.canonical_v2_deps.get_canonical_v2_candidate_chat_adapter
backend.main._create_canonical_v2_route_shell
backend.main.create_canonical_v2_candidate_app
legacy_consumer_quarantine.load_legacy_consumer_inventory
legacy-consumer-inventory-v1.json
```

- [x] Add one strict-xfail owner named:

```python
def test_s11b_candidate_app_exposes_only_release_bound_v2_consumers(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ...
```

It must enumerate the real candidate app, require the S11A/S10O/S11B route set, reject every legacy
writer/router prefix, and prove a V2 domain/detail/feedback vertical over one release.

The Admin owner module's top level imports only the standard library, pytest, and the `TestClient`
type; it has no `backend` or `src` import. It uses only built-in `request`, `tmp_path`, and
`monkeypatch` fixtures. Its dynamic seam loader completes successfully before dynamically importing
`backend.main` or constructing `TestClient`; `--noconftest` prevents the current Admin conftest from
eagerly importing `backend.main` ahead of the sentinel.

Before RED effects, it also asserts that Accepted `get_knowledge_gap_operations` remains exported
and has an exact zero-argument signature, `_compose_operations` remains present, the new request
gap getter and candidate-chat getter each have exactly one `Request` parameter, Accepted direct-state
`get_canonical_v2_chat_adapter` is unchanged, and candidate construction installs both exact
override identities. Module `app` has neither override; a direct-state valid chat adapter cannot
rescue missing/wrong candidate aggregate state.

- [x] Add one strict-xfail boundary owner named:

```python
def test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

It must discover executable scripts/imports and fail on the first unclassified or accepted-path
legacy writer/retrieval/index dependency.

- [x] Run normal RED:

```bash
cd apps/admin-console
uv run pytest -o addopts='' -p no:cacheprovider --noconftest -q \
  tests/test_canonical_v2_consumer_migration.py \
  -k s11b_candidate_app_exposes_only_release_bound_v2_consumers
cd ../miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -q \
  tests/canonical_v2/test_consumer_migration_boundary.py \
  -k s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers
```

Expected: exactly `1 xfailed` in each command, zero failures/errors/XPASS.

- [x] Run exact forced RED:

```bash
cd apps/admin-console
uv run pytest -o addopts='' -p no:cacheprovider --noconftest -q \
  tests/test_canonical_v2_consumer_migration.py \
  -k s11b_candidate_app_exposes_only_release_bound_v2_consumers --runxfail
cd ../miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -q \
  tests/canonical_v2/test_consumer_migration_boundary.py \
  -k s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers --runxfail
```

  Expected: exactly one named missing-seam failure per command, before SQL, provider, source, index,
  legacy import, or subprocess effects.

## Task 3: Implement the versioned quarantine inventory and guards

**Create:**

- `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/legacy-consumer-inventory-v1.json`
- `apps/miroflow-agent/src/data_agents/canonical_v2/legacy_consumer_quarantine.py`

- [x] Define one immutable JSON schema with these exact top-level fields:

```json
{
  "schema_version": "canonical-v2-legacy-consumer-inventory-v1",
  "retired_http_routers": [],
  "retired_frontend_routes": [],
  "legacy_modules": [],
  "legacy_scripts": [],
  "sanctioned_entrypoints": []
}
```

Each retired entry contains an exact path/module, one of `reference_only`, `replaced`, or
`s11c_disposition`, a non-empty reason, and either a sanctioned replacement or explicit absence of
one. Duplicate paths, unknown dispositions, globs that hide unreviewed files, or a retired path also
listed as sanctioned are invalid.

- [x] Populate all registered route modules and every discovered executable script that imports the
  audited legacy writer/retrieval/index surfaces or contains a direct V001-V042/fixed-collection
  mutation. Include the high-risk scripts named in the audit and all additional discovered siblings.
- [x] Sanction exactly:

```text
Accepted S11A /api/chat and session reset
Accepted S10O /api/canonical-v2/operations/gaps list/detail
S11B /api/canonical-v2/admin read endpoints and server-bound feedback
run_canonical_v2_evidence_ingest.py
smoke_canonical_v2_candidate.py
capture_canonical_v2_s11b_baseline.py
```

Do not sanction a generic legacy module directory, `run_*.py`, direct SQL helper, or Milvus client.

- [x] Implement a small loader that content-hashes and validates the inventory. It is a test/static
  policy input only; it is not a runtime feature flag and cannot enable a retired entrypoint.
- [x] Canonicalize before validation and hashing. File identities are exact-case repository-relative
  POSIX paths; reject absolute paths, backslashes, empty/`.`/`..` segments, repeated separators,
  NULs, symlink aliases, and repository escapes. Module identities are dot-separated Python
  identifiers. Require exactly one `path` or `module` per entry, prefix canonical identity with
  `path:` or `module:`, sort each category by that identity, and reject any duplicate across all
  retired/sanctioned categories. Canonical bytes are UTF-8 JSON with `ensure_ascii=False`, sorted
  keys, compact separators, `allow_nan=False`, and exactly one trailing LF. Reject source bytes that
  differ from canonical reserialization; receipt/discovery/S11C all use this same identity.
- [x] Expose an immutable inventory receipt containing the exact raw-byte inventory path/SHA-256,
  category counts, disposition counts, and exact lexicographically sorted
  `{"inventory_category": <top-level category>, "inventory_path": <path-or-module>}` pairs/count for
  `s11c_disposition`. Persist this as the `legacy_consumer_inventory` receipt subtree, with its hash
  at exact JSON pointer `/legacy_consumer_inventory/sha256`; S11C owns the separate complete overlay
  and retired-test disposition without editing or rebaselining this inventory.

```json
{
  "legacy_consumer_inventory": {
    "path": "<exact repository-relative inventory path>",
    "sha256": "<raw-byte SHA-256>",
    "category_counts": {},
    "disposition_counts": {},
    "s11c_disposition_entries": [
      {
        "inventory_category": "<top-level category>",
        "inventory_path": "<exact path-or-module>"
      }
    ],
    "s11c_disposition_count": 0
  }
}
```

  The array is sorted by `(inventory_category, inventory_path)` and the count equals its length; the
  shown zero is the valid empty example, not a requirement to rewrite a non-empty immutable base.
- [x] Make the boundary owner enumerate the complete 116-Python/24-shell baseline plus the three new
  sanctioned Python CLIs. Parse Python with AST-based import, dynamic-import, subprocess-target, and
  body inspection. Scan shell deterministically for repository-relative command targets, legacy
  script/module names, generic target variables, V001-V042/table markers, and fixed collection/index
  commands. Execute neither kind of retired script. Require exhaustive classification and prove the
  candidate app plus three sanctioned CLIs import none of:

```text
src.data_agents.canonical
domain canonical_writer/release/quality_promotion modules
src.data_agents.service.retrieval/search_service
src.data_agents.publish
legacy Milvus collection/store/vectorizer/backfill modules
backend legacy router modules or get_retrieval_service
```

  The candidate import closure must also exclude `backend.api.chat` and `backend.deps`; S11A chat,
  contracts, and dependencies are imported only through their V2-only modules.

- [x] Keep the boundary owner strict-xfailed after the inventory/loader exists: its seam/DAG also
  requires complete evidence-ingest, candidate-smoke, and baseline-capture CLIs. Task 7 alone removes
  this xfail after all three executable entrypoints and their focused owners are complete. Do not
  weaken the boundary owner into an inventory-only GREEN.

## Task 4: Implement the verified aggregate release-bound consumer runtime

**Create:** `apps/admin-console/backend/services/canonical_v2_admin.py`

- [x] Define private protocols for the already-Accepted planner, `KnowledgeRead`, and S10O operations;
  do not add another shared/public runtime framework.
- [x] Define one immutable aggregate runtime/factory constructed with exact typed inputs:

```python
def compose_canonical_v2_consumer_runtime(
    *,
    published_release: PublishedRelease,
    release_verification: ReleaseVerification,
    release_bundle: IsolatedReleaseBundle,
    index_projection_request: IndexProjectionRequest,
    planner: QueryPlannerPort,
    knowledge_read: KnowledgeRead,
    answer_factory: Callable[[], KnowledgeAnswer],
    answer_session_fork: Callable[[KnowledgeAnswer], KnowledgeAnswer],
    gap_operations: PostgresKnowledgeGapOperations,
    supplemental_budget: SupplementalBudget,
) -> CanonicalV2ConsumerRuntime: ...
```

At construction, exact-model-round-trip all four release inputs; require one active/rolled-back
accepted release, exact verification/publication evidence-ID equality, and a matching release/
manifest/index/candidate projection. Derive `BuildManifest` and `CandidateProjectionResult` only
from the verified bundle/request graph and `RelationshipProjectionResult` only from the bundle.
Reject loose supplied derivatives, missing relationship authority, manifest/projection mismatch, a
fifth public domain, or a runtime that discovers any dependency from environment state. The result
contains the controlled planner, one S11A chat adapter, one S11B admin runtime, and the exact same
S10O gap-operations object.

- [x] Before touching any injected port, require exact (not subclass) instances and hostile
  same-class-safe JSON round-trips for the four artifacts. Recompute manifest canonical SHA-256 over
  `manifest.model_dump(mode="json", exclude={"manifest_sha256"})`; require
  `release_verification.accepted`, exact candidate/release/manifest identities, and exact sorted
  verification evidence IDs equal to the publication. Replay
  `compose_candidate_projections(index_projection_request.candidate_projection_request)` and require
  equality with its supplied result. Require the bundle's non-null relationship request/result to
  bind that candidate request's exact internal-reference request/result pair. Replay
  `create_ephemeral_index_projection_builder().build(index_projection_request)` and require equality
  with `release_bundle.index_result`. Compare the exact seven candidate published manifests to the
  exact seven bundle-manifest published manifests. Reject wrong type, hostile same-class,
  model-constructed/forged manifest, cross release, missing/drifted relationship, replay drift, and
  fifth domain with zero planner/read/answer/gap calls.

- [x] Treat planner/read/answer/gap objects only as opaque ports; do not type-introspect or invoke
  them during construction. Before read, exact-revalidate each plan and compare its
  `PlanningReleaseBinding` to the derived publication state/hash/evidence IDs, manifest SHA, index
  request/result hashes, candidate result hash, and internal-reference result hash, not merely
  `release_id`. After read, validate the `EvidenceSet` exact typed round-trip, release/query
  continuity, closed trace/evidence references, and all available typed receipts before answer or
  response. Validate answer release/claim/evidence closure before copy-on-write session commit.
  Resolve and validate the immutable same-release feedback checkpoint before gap record.

- [x] Add one production `_ServerOwnedPlanControls` planner wrapper in this module. It delegates to
  the real release-bound planner and exact-revalidates every returned `RetrievalPlan` with the
  explicitly supplied server-owned `SupplementalBudget`. Only when the real plan already carries
  exactly the typed `company_has_patent/company_to_patent` Company→Patent path and a non-empty
  displayed Company canonical-ID set, bind a caller-owned representative `EnumerationPolicy` with
  exact scope `representative Patents naming one displayed Company as applicant`, the plan's `as_of`,
  `exhaustive=False`, and `continuation_state="available"`. Do not inspect query wording or change
  an Accepted planner algorithm. Treat this as the only runtime-authored enumeration-policy
  replacement; preserve incoming planner policies exactly on the other three Accepted public
  relationship paths required by Accepted S8R3/S8R4/S8R5, and preserve absence on non-enumeration
  plans. The S11B demo uses the exact values `1000 ms`, `2` provider calls, `1` retry, and `5.0` cost
  units. S12 must supply and record final candidate values through this same factory; neither
  control may remain test-only.

- [x] Add bounded typed methods for:

```text
status()
list_domain(domain, query, filters, sort, limit, offset)
get_domain(domain, canonical_id)
facet(domain, typed_field)
related(domain, canonical_id, relation_type, limit)
export_domain(domain, ids, format)
record_chat_feedback(session_id, feedback_type, note)
```

Object search/list and detail create an accepted typed plan through the injected release-bound
planner and execute it through `KnowledgeRead.execute`. The exact typed projections validate the
returned identities/release and own deterministic facets, export rows, projection hashes, and field
lineage. Allowlisted filters and sort keys come from each projection model; arbitrary JSON paths are
rejected. Return release, projection version/hash, as-of, typed values, field lineage/evidence,
quality signal/limitations, and bounded counts. Do not synthesize absent V042 fields.

- [x] `related` must validate the source ID is displayed/accepted and the typed relation exists in
  the exact same release, then execute the accepted typed relationship plan through
  `KnowledgeRead.execute`. Never call the legacy retrieval service, direct relation SQL, or a lane
  adapter. Return evidence/release/trace IDs.
- [x] `record_chat_feedback` must call the read-only
  `chat_adapter.get_feedback_checkpoint(session_id)` and derive a typed S10O `GapSignal` from the
  immutable `ChatFeedbackCheckpoint`. Trust only its release, query/answer trace IDs, evidence IDs,
  domains/paths, limitation codes, observation time, and content hash. The client may supply feedback
  type and bounded note; client answer/citation/structured JSON cannot establish lineage. No setter,
  mutable checkpoint, or adapter-private map access is permitted.
- [x] Add no database pool, SQL, Milvus client, provider, canonical writer, active pointer, global
  readiness, queue, scheduler, auth redesign, or cross-process cache.

- [x] Freeze the admin request allowlists and bounds in code, not reflection or arbitrary JSON:
  domains exactly `company|paper|patent|professor`; `q` and canonical/filter values at most 200
  characters; at most four complete filter pairs; `order=asc|desc`; list `limit=1..100` default 25;
  `offset=0..10000` and `offset+limit<=10000`; related `limit=1..50` default 20; facet output at most
  100 buckets ordered by `(-count, normalized_value)`; export requires 1..500 unique IDs and
  `format=jsonl`, with no alternate format or implicit all. Each line is canonical typed projection JSON.
- [x] Freeze domain fields exactly: Company filters/facets `industry|geography|quality_status`, sorts
  `name|founded_at|last_updated`, with NamedReference values matched by exact `reference_id`; Paper
  filters/facets `venue|year|quality_status`, with venue matched by exact `reference_id` and year a
  typed integer `1000..9999`, sorts `title|year|citation_count|last_updated`; Patent filters/facets
  `patent_type|publication_date|quality_status`, sorts
  `title|publication_date|filing_date|last_updated`; Professor filters/facets
  `institution|department|quality_status`, with department matched by exact `reference_id`, sorts
  `name|h_index|citation_count|last_updated`. Year/date filtering and sorting are typed; every sort
  ends with `canonical_identity_id ASC` regardless of primary direction.
  Related allows only `company_has_patent` for company↔patent and
  `professor_authored_paper` for professor↔paper, with direction derived from source domain.

## Task 5: Register the candidate app and migrate the HTTP surface

**Create/modify:**

- `apps/admin-console/backend/api/canonical_v2_consumers.py`
- `apps/admin-console/backend/canonical_v2_deps.py`
- `apps/admin-console/backend/main.py`
- `apps/admin-console/backend/api/canonical_v2_chat.py`
- `apps/admin-console/backend/static/browse.html`

- [x] Preserve/export Accepted zero-argument `get_knowledge_gap_operations()` and
  `_compose_operations()` unchanged. Add exact
  `get_canonical_v2_gap_operations(request: Request)`. Preserve Accepted
  `get_canonical_v2_chat_adapter(request: Request)` unchanged as the direct-state predecessor seam;
  add distinct `get_canonical_v2_candidate_chat_adapter(request: Request)`, which resolves only the
  aggregate chat member. Both new candidate getters return stable
  `canonical_v2_runtime_unavailable` `503` on missing/wrong aggregate with no direct-state,
  environment, composer, storage, or legacy fallback.
- [x] In `backend/main.py`, define V2-only `_create_canonical_v2_route_shell()` and
  `create_canonical_v2_candidate_app(*, runtime: CanonicalV2ConsumerRuntime)`. The factory creates a
  fresh shell, sets its exact aggregate, and installs only these identities:

```python
app.dependency_overrides[get_canonical_v2_chat_adapter] = (
    get_canonical_v2_candidate_chat_adapter
)
app.dependency_overrides[get_knowledge_gap_operations] = (
    get_canonical_v2_gap_operations
)
```

  Module `app = _create_canonical_v2_route_shell()` has no aggregate and no overrides, remains
  V2-only, and preserves the exact direct-state S11A and zero-arg S10O owners. S11B owner, smoke, and
  import-graph evidence use `create_canonical_v2_candidate_app`, never module `app`. A valid direct
  chat adapter plus missing/wrong aggregate on a candidate still returns the stable aggregate `503`,
  proving no fallback. S12 owns the final installed entrypoint.
- [x] Add bounded V2 endpoints:

```text
GET  /api/canonical-v2/admin/status
GET  /api/canonical-v2/admin/domains/{domain}
GET  /api/canonical-v2/admin/domains/{domain}/facets/{field}
GET  /api/canonical-v2/admin/domains/{domain}/export
GET  /api/canonical-v2/admin/domains/{domain}/{canonical_id}
GET  /api/canonical-v2/admin/domains/{domain}/{canonical_id}/related
```

Use Pydantic response models, bounded limit/offset and export size, typed domain/filter/relation
allowlists, stable 404/422/503 errors, and sanitized exception mapping. There is no PATCH, DELETE,
batch quality, upload, build, promote, alias, or arbitrary SQL route.

  Register the static `/export` route before the dynamic `/{canonical_id}` route and own a test that
  proves the literal `export` is never parsed as an object ID.

- [x] Preserve Accepted S11A `POST /api/chat` and reset exactly. Migrate `/api/chat/feedback` to
  `CanonicalV2AdminRuntime.record_chat_feedback`; retain the current client request envelope during
  the UI transition but ignore client-authored answer/citation/lineage fields.
- [x] In the candidate `app`, import/register only health, S11A's V2-only chat router, S10O
  operations, and S11B consumer routers. It never imports `backend.api.chat` or `backend.deps`.
  Remove imports/registration of admin-professor, batch, dashboard, data, domains, export, pipeline,
  pipeline-issues, review, seeds, and upload routers. Do not start `seed_cron`.
- [x] Remove the accepted app's import-time `MILVUS_USE_REAL_CLIENT` mutation and legacy
  `get_retrieval_service` factories. Historical tests may import retired modules directly until S11C,
  but the candidate app cannot.
- [x] Construct FastAPI with `openapi_url=None`, `docs_url=None`, and `redoc_url=None`. The complete
  known API allowlist is exactly:

```text
GET  /api/health
POST /api/chat
POST /api/chat/feedback
POST /api/chat/session/reset
GET  /api/canonical-v2/operations/gaps
GET  /api/canonical-v2/operations/gaps/{gap_id}
GET  /api/canonical-v2/admin/status
GET  /api/canonical-v2/admin/domains/{domain}
GET  /api/canonical-v2/admin/domains/{domain}/facets/{field}
GET  /api/canonical-v2/admin/domains/{domain}/export
GET  /api/canonical-v2/admin/domains/{domain}/{canonical_id}
GET  /api/canonical-v2/admin/domains/{domain}/{canonical_id}/related
```

  Outside `/api`, allow exactly `GET /`, `GET /browse`, `GET /chat`, and the `/static` mount. No
  framework docs/OpenAPI or React SPA route is registered.
- [x] Remove the legacy global permissive `CORSMiddleware`; all retained built-in pages are
  same-origin. The unknown-route owner sends `OPTIONS` both with and without CORS preflight headers
  and requires the same typed `404`, so middleware cannot turn an unknown API into success.
- [x] Update `browse.html` to call the new status/domain endpoints and render release/as-of/evidence
  limitations with safe text escaping. It must not call legacy aliases or expose mutation controls.
- [x] Register one reject-only `/api/{path:path}` handler after all known API routes and before every
  static route for exactly `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, and `DELETE`. Every
  invocation returns the same typed `404` without resolving a runtime or performing an effect.
  Unknown APIs never return `405`, HTML, or a successful SPA fallback. The route owner treats this
  sink as an explicit non-writer allowlist entry. Do not mount/import the legacy React SPA.

## Task 6: Complete the minimal built-in candidate UI

**Modify:** `apps/admin-console/backend/static/browse.html`

- [x] Render release/status, four read-only domain populations, bounded detail/related evidence, and
  S10O gap list/detail from the V2 endpoints. Preserve the S11A static chat surface separately.
- [x] Use DOM text nodes or equivalent escaping for every server value. Show typed limitations and
  bounded runtime-unavailable/error states; expose no edit/delete/upload/batch/build/promote/index/
  seed/pipeline control.
- [x] Own the page through backend/static tests that inspect/fetch the actual candidate artifact and
  prove it contains only sanctioned V2 API paths, no legacy endpoint string, and no mutation action.
- [x] Keep `apps/admin-console/frontend/**` byte-identical and classify it `reference_only` in the
  inventory. Recompute the 22-file `frontend/src/**` sorted path-plus-raw-file-SHA-256 digest and
  require the Specified value
  `99abf5922399cd8bf20990934fa251c2a246da300fd4af3af384e6a9478ead77`. The candidate app does not
  mount/import it. No npm, Vitest, Vite, or React build is a required S11B check.

## Task 7: Implement all three sanctioned CLIs and close the boundary DAG

**Create/tests:**

- `apps/miroflow-agent/scripts/run_canonical_v2_evidence_ingest.py`
- `apps/miroflow-agent/tests/scripts/test_run_canonical_v2_evidence_ingest.py`
- `apps/admin-console/scripts/smoke_canonical_v2_candidate.py`
- `apps/admin-console/tests/test_smoke_canonical_v2_candidate.py`
- `apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py`
- `apps/miroflow-agent/tests/scripts/test_capture_canonical_v2_s11b_baseline.py`

- [x] For evidence ingestion, require explicit CLI flags for database URL, expected database,
  target kind, backup-gate root, request JSON, S2B `source-id`, `member-namespace`, and
  `member-relative-path`. There is no arbitrary content-file flag. Do not read `DATABASE_URL`,
  `DATABASE_URL_TEST`, original source paths, or a default database.
- [x] Define one CLI-local metadata model containing every applicable `IngestEvidenceRequest` field
  except `content`. Reject any request JSON containing `content`; require a non-null
  `expected_content_sha256`; retain strict unknown-field rejection.
- [x] Enforce this exact effect order: (1) validate required flags and CLI-local metadata without
  opening content; (2) call `create_postgres_evidence_landing(...)` exactly once, which resolves the
  explicit target and passes the S2B backup gate/connect check, then retain that adapter; (3)
  content-bind the accepted S2B backup manifest, restore verification, and acceptance record; select
  exactly one member-manifest row by `(source_id, namespace, relative_path)`; require request
  `source_locator` to equal exactly
  `s2b-restore://{accepted_run_id}/{namespace}/{relative_path}`; derive only
  `restore_root / namespace / relative_path`; require its restore source row to be `passed`,
  `hash_verified=true`, and `copy_independent=true`; (4) `lstat`, require current size to equal the
  member row and the restore inode/device to differ from original, backup object, and member-manifest
  files, reject symlink/non-regular/original/backup/object/alias escape, read the restore member
  exactly once, and verify current SHA-256 against both the manifest member hash and
  `expected_content_sha256`; (5) construct the real
  `IngestEvidenceRequest` from the validated metadata plus those same bytes, call the retained
  adapter's `ingest` exactly once, and print only the exact `LandingReceipt` JSON. Typed/sanitized
  errors exit non-zero before any partial fallback. Do not duplicate the factory's target/connect
  implementation in the CLI.
- [x] Test missing/ambiguous/generic/original target rejection, expected-database mismatch, missing
  accepted backup gate, unknown/duplicate S2B source/member, manifest/restore/acceptance hash drift,
  non-passed restore source, arbitrary non-member staging, wrong locator/size/inode, symlink/
  non-regular/original/backup/
  object/alias escape, content-hash mismatch, gate-before-open ordering, exactly-one-read,
  successful disposable/candidate ingest, idempotent replay, and unchanged active release/
  canonical/index state.
- [x] For the smoke caller, require `--base-url` and `--expected-release-id`; accept a bounded query
  list, use one cookie session, and require HTTP `200` plus the same V2 release and non-empty bounded
  plan/lane/evidence/claim trace. It is a transport/product smoke, not a prose or quality oracle.
- [x] The smoke caller must not import the admin app, load a DSN/index, start a provider, infer the
  latest release, or use reference prose/golden answers.
- [x] Implement the fixed/guarded baseline producer contract from Task 9 and pass its focused owner;
  Task 9 executes the broad partitions but does not create this third CLI.
- [x] Run all three focused CLI owner files with warnings as errors. Expected: all pass with no skip/
  xfail/XPASS and no network beyond the test-local HTTP server.
- [x] Only after the inventory/loader and all three CLIs/owners are complete, remove strict-xfail
  from `test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers` and run its exact
  nodeid with:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error -q \
  tests/canonical_v2/test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers
```

  Expected: pass with no skip/xfail/XPASS. Missing any one executable keeps the boundary owner
  strict-xfailed.

## Task 8: Complete the observable candidate-consumer vertical

**Test:** `apps/admin-console/tests/test_canonical_v2_consumer_migration.py`

- [x] Remove strict-xfail only after all seams exist. Install one explicit fixture runtime composed
  through `compose_canonical_v2_consumer_runtime` from actual Accepted S11A/S10O interfaces plus an
  exact accepted `PublishedRelease`, `ReleaseVerification`, `IsolatedReleaseBundle`, and matching
  `IndexProjectionRequest`. Test-local loose projection/relation inputs, fake admin data models,
  test-only plan-control wrappers, or legacy SQL are forbidden.
- [x] Construct the tested app only with `create_canonical_v2_candidate_app(runtime=...)`; never
  mutate/reuse module `app`. Prove both override identities, module-shell compatibility, and that a
  valid direct chat state cannot rescue missing/wrong candidate aggregate state.
- [x] Through the real candidate FastAPI app, execute:

```text
status -> one accepted release and manifest
domain list -> four-domain typed projection page
domain detail -> same release, evidence/field lineage, honest limitations
related -> same release, accepted typed relation and retrieval/evidence trace
chat -> S11A V2 release/plan/lanes/evidence/claims
feedback -> S10O typed gap bound to the server-retained chat trace
gap detail -> same release and exact feedback lineage
```

  Assert the observable chat/admin plans carry the runtime-bound `SupplementalBudget`; the typed
  displayed Company→Patent relationship turn additionally carries the exact representative
  `EnumerationPolicy`, while ineligible turns do not. App-state chat/admin/gap members must be the
  identities installed by the one aggregate runtime.

- [x] Make `get_pg_conn`, `get_retrieval_service`, every retired router endpoint, legacy chat callable,
  legacy domain writer, direct Milvus builder, and subprocess launcher raise if reached. The vertical
  must still pass.
- [x] Add negative groups for missing/wrong runtime, cross-release manifest/projection/relationship,
  fifth public domain, arbitrary filter/relation, client-forged feedback lineage, old mutation URLs,
  static `export` captured as a canonical ID, unknown `/api/*` returning HTML/success, and
  original/fixed-index target references. Fail before downstream effects.
- [x] Add graph-construction negatives for wrong type, subclass/hostile same-class, forged canonical
  manifest hash, verification rejected/candidate/release/manifest/evidence mismatch, candidate replay
  drift, index replay drift, missing/cross-wired relationship internal pair, relationship-result
  drift, and fifth domain. Assert zero planner/read/answer/gap effects for every constructor failure.
- [x] Add exact effect counters: plan/release-binding mismatch is observed after one plan call and
  before read; EvidenceSet release/query/trace/evidence/receipt mismatch is after one read and before
  answer/HTTP response; answer release/claim/evidence mismatch is before session commit; absent or
  cross-release checkpoint is before gap record. Compare the complete `PlanningReleaseBinding`
  derived fields, not only `release_id`.
- [x] Assert the new gap getter's missing/wrong aggregate cases return the stable aggregate `503`
  with zero env/SQL/provider effects; its success result is the exact aggregate member. Make
  `_compose_operations` raise and prove the candidate gap route still succeeds. Also rerun the
  unchanged direct S10O owner and prove the override key/value identities are exact.
- [x] Enumerate routes and assert there is no candidate POST/PATCH/DELETE data/index/build path other
  than S11A reset/chat/feedback and no feedback path that writes canonical or Milvus.
- [x] Assert the candidate import closure never loads `backend.api.chat`, `backend.deps`, or legacy
  React assets; `/export` precedes the dynamic detail route; unknown `/api/*` returns exact `404`.
- [x] Run exact Admin GREEN:

```bash
cd apps/admin-console
uv run pytest -o addopts='' -p no:cacheprovider --noconftest -W error -q \
  tests/test_canonical_v2_consumer_migration.py::test_s11b_candidate_app_exposes_only_release_bound_v2_consumers
```

  Expected: pass with no skip/xfail/XPASS. This exact owner command, unlike the broad baseline, never
  loads Admin conftest.

## Task 9: Run proportional migration verification

- [x] Rerun final Accepted S10O and S11A owner commands exactly from their receipts. Expected: exit
  `0`; do not alter predecessor assertions to fit S11B.
- [x] Run the complete no-external candidate admin-console suite and complete no-external Canonical
  V2 suite using the final predecessor commands. Historical tests that import intentionally retired
  routers/scripts may fail; record them for S11C and do not weaken them or re-register old paths.
- [x] Run only the Task 7-complete `capture_canonical_v2_s11b_baseline.py` to produce the broad-baseline
  artifacts. Its fixed run table has the complete Canonical V2 no-external partition and the Admin
  partition with exact marker expression `-m "not requires_classifier_llm"`; neither uses `-k` or a
  known-failure/node-ID filter. Admin collection records the unique deselected classifier node.
- [x] Before pytest collection, the producer must set `PYTHON_DOTENV_DISABLED=1`, hold every member
  of the Slice Contract's literal sorted 49-name `SENSITIVE_ENV_NAMES` tuple present-empty, and
  require the receipt list to equal `list(SENSITIVE_ENV_NAMES)` exactly. Socket guard v2 may permit
  AF_INET `connect` only to numeric `127.0.0.1:<exact port>` when the matching socket object in the
  same child called patched `listen` after guard installation, remains live, and has
  `SO_ACCEPTCONN=1`; this exception is solely for the required black-box candidate smoke test.
  Fail closed on AF_INET6, unowned/closed/wrong-port/non-loopback AF_INET, every inet `connect_ex`,
  and every psycopg connection attempt. Keep AF_UNIX allowed only inside an exact producer-owned
  temporary root. Create that root as a fresh
  `0700` `/tmp/s11b-*` directory, never ambient `/tmp` itself, and require the encoded
  `guard-probe.sock` path to remain within Linux's 107-byte AF_UNIX limit. Before child startup bind
  `TMPDIR`, `TMP`, `TEMP`, exact child-stage paths, and the intended pytest temp root beneath it.
  Install the guard in `pytest_load_initial_conftests`, then use `tryfirst` `pytest_configure` to
  replace `config.option.basetemp` with `CANONICAL_V2_S11B_PYTEST_TEMP` and, for run mode, replace
  `config.option.xmlpath` with `CANONICAL_V2_S11B_JUNIT_STAGE` before collection, fixture, or JUnit
  write effects, so Milvus Lite sockets cannot use ambient `/tmp`. Record the exact resolved root,
  variable values, environment-name set, guard
  versions, marker exclusion, collection count, deselected node, and preflight self-probes in the
  guard receipt. Remove inherited `PYTEST_CURRENT_TEST`; at session finish restore all sensitive
  names to present-empty before the session-finish receipt update, including proxy names intentionally deleted
  by legacy tests. Child schema
  `canonical-v2-s11b-child-guard-v3` and JUnit-recomputable baseline signature v3 retain socket guard v2 and add
  `attempt_attribution=pytest-current-test-report-v1`. Use one process-local `threading.RLock` to
  serialize every guard-state mutation with its receipt snapshot/write and preserve all concurrent
  duplicate attempts as valid JSON. Do not restore the patched socket/psycopg/dotenv guards in
  `pytest_unconfigure`; keep them and the live guard state installed through process exit, including
  late workers and `atexit` callbacks. Physically block any unattributed late attempt, record it in
  `forbidden_attempts`, and make the parent reject that run. Treat only the bytes read by the parent
  after the subprocess has fully exited as the terminal child receipt. Put a non-probe socket/psycopg attempt in
  `blocked_test_attempts` only after blocking it before effect while pytest's exact active run-mode
  `call` context is visible, including worker threads spawned during that call. Require collected
  membership, exactly one matching report row with a valid
  outcome, and child exitstatus equal to subprocess returncode; aggregate exact run ID/outcome/count
  without deduplicating repeated attempts. Keep `forbidden_attempts=[]`. Collection-time,
  setup/teardown, post-call worker, unattributed, unsupported, or unreported attempts must fail
  closed, and collection permits no blocked-test or owned-loopback rows. A guard/preflight failure,
  collection drift, interruption, or missing artifact exits non-zero and emits no baseline run. The earlier
  dotenv-restored real-DSN aborted run is explicitly ineligible evidence.
- [x] Freeze exact partitions. `canonical-v2-no-external` uses cwd `apps/miroflow-agent` and argv
  `["uv","run","pytest","-o","addopts=","-p","no:cacheprovider","-q","--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/tmp/canonical-v2-no-external/pytest","--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/canonical-v2-no-external.xml","tests/canonical_v2"]`.
  `admin-no-external` uses cwd `apps/admin-console` and argv
  `["uv","run","pytest","-o","addopts=","-p","no:cacheprovider","-q","-m","not requires_classifier_llm","--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/tmp/admin-no-external/pytest","--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/admin-no-external.xml","tests"]`.
  Treat the literal basetemp/JUnit values in both frozen argv arrays as audit sentinel tokens, not
  write destinations. The early plugin must perform the exact option rebinding above, and collect
  mode disables JUnit output; otherwise the guard receipt is invalid.
  Each collection argv removes its JUnit token and inserts `--collect-only` immediately before the
  test path. No alternate cwd, marker, plugin, `-k`, node ID, or known-failure selection is valid.
- [x] Nodeid artifacts are UTF-8, lexicographically sorted unique, one exact LF-terminated nodeid per line,
  no summary. Map every collected nodeid through pytest's exact JUnit address mangling to one unique
  `(classname,name)` testcase and map every testcase back; never zip by document/sort position.
  Require one setup and teardown report per executed nodeid, plus exactly one call report iff setup
  passed, with no duplicate phase; the derived terminal `passed|skipped|failure|error` outcome must
  equal the JUnit child outcome. Every failure/error annotation belongs to its parent testcase and
  matches one exact identity/lifecycle report row. Normalize only the three frozen substitutions and hash
  `outcome + LF + normalized_message + LF + normalized_body`; phase is stored separately and is not
  part of the hash. Derive message/body from the persisted JUnit failure/error element so S11C can
  independently recompute the hash; use the ephemeral report hook only for nodeid/phase/outcome and
  lifecycle bijection. Missing, duplicate, ambiguous, partial, or mismatched output fails closed.
  Require collection exit `0` and run exit only `0|1`; reject pytest codes `2|3|4|5` and signal
  exits even when receipt and subprocess agree. Wrap the original
  `dotenv.load_dotenv`, capture any tuple-member mutation, and in `finally` restore all 49 members to
  their exact pre-call present-empty state before recording/raising; preflight proves a no-op, while
  RED mutates the environment, observes the guard error, and asserts every member still equals `""`.
  All four `CANONICAL_V2_TEST_*` gates stay empty in B6; explicit disposable-DB acceptance is a
  separate workflow and not a baseline-producer branch.
- [x] Before a run, create a fresh exclusive child stage beneath `/tmp/s11b-*` plus a separate
  parent-only stage on the output filesystem, and reject any pre-existing stage, final nodeid/JUnit
  target, or baseline row. Let the child write only beneath the owned `/tmp` stage/temp tree; parse
  all output and prove the
  complete nodeid/JUnit/report-hook bijection; then copy validated child artifacts into a
  parent-only stage on the output filesystem, verify byte-identical SHA-256, promote with
  same-filesystem hard links without overwrite, and expose the baseline row last. In `finally`,
  terminate only owned child processes and remove the
  unpromoted stage and owned `TMPDIR`/`TMP`/`TEMP`/`--basetemp` tree on success, failure, and
  interruption. On any failure,
  remove every newly promoted nodeid/JUnit artifact, emit no row, and preserve pre-existing bytes.
  Record `cleanup=true` only after zero owned children/stage/temp roots are proved.
- [x] Run static checks on every changed Python file:

```bash
cd apps/admin-console
uv run ruff check \
  backend/api/canonical_v2_consumers.py backend/services/canonical_v2_admin.py \
  backend/api/canonical_v2_chat.py backend/canonical_v2_deps.py backend/main.py \
  tests/test_canonical_v2_consumer_migration.py \
  scripts/smoke_canonical_v2_candidate.py tests/test_smoke_canonical_v2_candidate.py
uv run ruff format --check \
  backend/api/canonical_v2_consumers.py backend/services/canonical_v2_admin.py \
  backend/api/canonical_v2_chat.py backend/canonical_v2_deps.py backend/main.py \
  tests/test_canonical_v2_consumer_migration.py \
  scripts/smoke_canonical_v2_candidate.py tests/test_smoke_canonical_v2_candidate.py
cd ../miroflow-agent
uv run ruff check \
  src/data_agents/canonical_v2/legacy_consumer_quarantine.py \
  scripts/run_canonical_v2_evidence_ingest.py \
  scripts/capture_canonical_v2_s11b_baseline.py \
  tests/canonical_v2/test_consumer_migration_boundary.py \
  tests/scripts/test_run_canonical_v2_evidence_ingest.py \
  tests/scripts/test_capture_canonical_v2_s11b_baseline.py
uv run ruff format --check \
  src/data_agents/canonical_v2/legacy_consumer_quarantine.py \
  scripts/run_canonical_v2_evidence_ingest.py \
  scripts/capture_canonical_v2_s11b_baseline.py \
  tests/canonical_v2/test_consumer_migration_boundary.py \
  tests/scripts/test_run_canonical_v2_evidence_ingest.py \
  tests/scripts/test_capture_canonical_v2_s11b_baseline.py
```

Every acceptance command must exit `0`.

- [x] Run `py_compile` and changed-scope Pyright for Python plus focused backend/static owners for
  `browse.html`. Expected: zero errors. React/npm/Vitest/Vite are not S11B acceptance checks.
- [x] Run route/import/quarantine guards proving:

```text
only S11A/S10O/S11B data routes are registered
no accepted route depends on get_pg_conn/get_retrieval_service or direct SQL
candidate imports neither backend.api.chat nor backend.deps nor legacy React
no accepted import reaches legacy canonical writers/fixed handlers/global readiness
no accepted command reaches old collection names/direct active-index mutation
every discovered legacy executable is classified
no generic/original database or Milvus fallback exists
static export precedes dynamic detail; all seven unknown /api/* methods return typed 404 before static
```

  The route receipt records the exact known API allowlist, exact static allowlist, disabled
  framework-doc configuration, absent permissive CORS bypass, reject-only sink methods/order, and
  proves every one of the seven methods returns typed `404` for an unknown path.

- [x] Run repository gates:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`.

- [x] Run the established scope, secret, generated-cache, fresh locked-offline wheel/package-content,
  source parity, and frozen original PostgreSQL/Milvus/forensic hash checks from the latest Accepted
  receipt. Expected: all protected state remains exact.
- [x] Perform one lean implementation/test-integrity review. Repair open Critical/Important only;
  record Minor/YAGNI without another review loop. Rerun the smallest affected checks after repair.

## Task 10: Candidate and Accepted without ledger closure

- [x] Record dependency hashes, exact RED/GREEN commands/results, changed-file hashes, route/import/
  inventory results including exact inventory hash/category/disposition counts and sorted
  category-plus-path `s11c_disposition` pairs/count, admin/chat/gap demo invariants, explicit-target
  CLI evidence, built-in UI results,
  regression/static/gate results, protected-source hashes, and review disposition in
  `s11b/verification-receipt.json`.
- [x] In that receipt, use exact JSON pointer `/legacy_consumer_inventory/sha256` for the raw-byte
  inventory authority. Record each broad baseline run under `broad_test_baseline.runs` with exact
  argv token array, real exit code, collected-nodeid artifact path/hash, JUnit artifact path/hash,
  and every failure/error's exact nodeid, outcome, and normalized signature SHA-256. Normalize only
  CRLF to LF, the exact run-mode `--basetemp` root to `<pytest-tmp>/` first, and the exact
  repository root to `<repo>/` second; take message/body from the persisted JUnit failure/error element and hash
  `outcome + LF + normalized_message + LF + normalized_body`. If no exact baseline row
  exists, record that `unrelated_preexisting` is unavailable rather than inventing one in S11C.
  Content-bind the producer and its guard/preflight evidence; unsafe or aborted runs cannot appear.

The shown numeric loopback port illustrates the required integer type; an emitted row contains the
exact ephemeral port observed in that child.

```json
{
  "broad_test_baseline": {
    "signature_schema_version": "canonical-v2-s11b-baseline-signature-v3",
    "producer_path": "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py",
    "producer_sha256": "<raw-byte SHA-256>",
    "guard_preflight": {
      "python_dotenv_disabled": "1",
      "present_empty_sensitive_env_names": ["<exact list(SENSITIVE_ENV_NAMES)>"],
      "blocked_socket_families": ["AF_INET", "AF_INET6"],
      "blocked_socket_operations": ["connect", "connect_ex"],
      "psycopg_connect_blocked": true,
      "owned_temp_root": "<exact resolved producer-owned root>",
      "temp_environment": {"TMPDIR": "<owned child>", "TMP": "<owned child>", "TEMP": "<owned child>"},
      "pytest_temp_roots": {
        "<run_id>": {
          "collect": "<exact collect --basetemp root>",
          "run": "<exact run --basetemp root used by signature normalization>"
        }
      },
      "allowed_af_unix_roots": ["<producer-owned temporary root>"],
      "admin_marker_expression": "not requires_classifier_llm",
      "admin_deselected_nodeids": ["tests/test_classifier_benchmark.py::test_classifier_benchmark"],
      "self_probes_passed": true,
      "cleanup": true,
      "blocked_test_attempt_count": 1,
      "blocked_test_attempts": [
        {
          "run_id": "admin-no-external",
          "kind": "af_inet_connect_blocked",
          "message": "AF_INET access is blocked",
          "nodeid": "tests/<exact-test>.py::test_<exact-name>",
          "phase": "call",
          "report_outcome": "passed"
        }
      ],
      "forbidden_attempts": [],
      "child_receipts": [
        {
          "schema_version": "canonical-v2-s11b-child-guard-v3",
          "socket_policy": {
            "af_inet_connect": "owned_live_loopback_listener_only",
            "af_inet_connect_ex": "blocked",
            "af_inet6_connect": "blocked",
            "af_unix_connect": "owned_root_only",
            "listener_requirements": {
              "destination_host": "127.0.0.1",
              "exact_destination_port": true,
              "listen_observed_after_guard_install": true,
              "live_socket_object": true,
              "same_process_socket_object": true,
              "so_acceptconn": true
            }
          },
          "allowed_owned_loopback_connects": [
            {
              "destination_host": "127.0.0.1",
              "destination_port": 49152,
              "family": "AF_INET",
              "listener_host": "127.0.0.1",
              "listener_port": 49152,
              "operation": "connect"
            }
          ],
          "guard_versions": {
            "socket": "stdlib-socket-guard-v2",
            "psycopg": "psycopg-sync-async-guard-v1",
            "dotenv": "dotenv-restore-guard-v1",
            "attempt_attribution": "pytest-current-test-report-v1"
          },
          "blocked_test_attempts": [
            {
              "kind": "af_inet_connect_blocked",
              "message": "AF_INET access is blocked",
              "nodeid": "tests/<exact-test>.py::test_<exact-name>",
              "phase": "call"
            }
          ],
          "forbidden_attempts": []
        }
      ]
    },
    "runs": [
      {
        "run_id": "<stable run id>",
        "cwd": "<exact repository-relative cwd>",
        "collection_argv": ["<exact collection argv token>"],
        "argv": ["<exact argv token>"],
        "exit_code": 0,
        "collected_nodeids_path": "<repository-relative path>",
        "collected_nodeids_sha256": "<raw-byte SHA-256>",
        "junit_xml_path": "<repository-relative path>",
        "junit_xml_sha256": "<raw-byte SHA-256>",
        "failures": [
          {
            "nodeid": "<exact nodeid>",
            "phase": "collection|setup|call|teardown",
            "outcome": "failure|error",
            "normalized_failure_signature_sha256": "<SHA-256>"
          }
        ]
      }
    ]
  }
}
```
- [x] Mark the S11B contract Candidate only after all required evidence exists. Do not check any task
  at Candidate.
- [x] Recheck the final diff is limited to authorized S11B consumer/API/UI/CLI/quarantine/test and
  status/evidence files. Confirm no Canonical V2 algorithm, migration, original source, index bytes,
  active pointer, or OpenSpec behavior artifact changed.
- [x] With zero open Critical/Important findings, mark S11B Accepted as the dependency checkpoint for
  S11C. Record the live ledger before/after with no delta and leave Tasks `11.1`-`11.5` unchecked.
- [x] Update only existing verification/portfolio/mainline/convergence/agent-link pointers needed to
  reference the Accepted S11B receipt. Do not claim aggregate consumer migration, complete candidate,
  or Cutover.
- [x] Run strict OpenSpec and `git diff --check` once more. Expected: both exit `0`.

## Rollback checkpoint

If S11B cannot reach Candidate, remove the new V2 admin router/service, restore the prior S11A/S10O
candidate app registration and built-in browse page, remove the three sanctioned
CLIs and quarantine inventory/tests, and restore the prior S11A feedback route. Re-registering legacy
data writers is only a development rollback for the pre-S11B comparison app; it is not acceptance or
Cutover. No database, index, source, provider, active pointer, task checkbox, Commit, Push, PR,
Archive, promotion, or production-like state requires rollback.
