# S11B Canonical V2 Consumer Migration and Legacy Quarantine Dependency Audit — 2026-07-20

## Outcome

The smallest honest second consumer slice is to make the candidate admin application import only
the S11A V2-only chat/contracts/dependency modules and expose only
three sanctioned consumer paths:

1. release-bound Canonical V2 chat from Accepted S11A;
2. release-bound, read-only administration over accepted typed projections and Accepted S10O gap
   operations; and
3. explicit-target offline evidence ingestion plus a black-box V2 HTTP smoke caller.

Everything that still writes V001-V042 tables, reads them as the serving model, invokes the legacy
`RetrievalService`, mutates a fixed Milvus collection/alias, or treats one global quality/readiness
flag as publication authority is quarantined from the candidate application and sanctioned CLI
surface. The source files may remain temporarily as historical comparison evidence for S11C; they
are not registered routes, imported dependencies, subprocess targets, documented operator commands,
or fallbacks.

S11B is **Accepted** at `2026-07-21T12:54:16Z` after the final receipt/state review reported
`Critical=0` and `Important=0`. Fresh signature-v3 baseline row
`a9bdfcdb5d2b8a6409811de6bf8c53bc66e7e2d78afa92edb9cc09cf0b06f668` independently replays all
22 Admin signatures from persisted JUnit with exact per-run basetemp mapping, temp-first/repo-second
normalization, and zero parent/signature mismatch. Canonical V2 collected 530
tests with exit `0`, while Admin collected 596 tests with exit `1` and retained 18 failures plus 4
setup errors for S11C disposition. All 22 failure/error annotations bind their exact parent
testcase; 15 blocked legacy negative-test attempts are attributable and `forbidden_attempts=[]`.
The earlier `2026-07-21T11:48:32Z` Candidate attempt and v2 row were rejected and deleted. The
formal ledger remains `65/80`, with Tasks `11.1`-`11.5` and acceptance unchanged. S11C remains
Specified and owns aggregate closure.

The historical Ready review remains useful design evidence, while Accepted S9J corrected the live
public-answer/chat-owner bytes after historical S11A acceptance. S11B depends on Accepted S10O,
historical Accepted S11A, and Accepted S9J, including
their final verification receipts. S10O owns durable typed gaps and the bounded operator read model;
S11A owns the registered release-bound chat route and typed server-side session checkpoint; S9J
owns the successor public-copy correction. S11B must not duplicate those contracts.

The exact Accepted S11A dependency is
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s11a/verification-receipt.json` at raw-byte
SHA-256 `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`. Its final
consumer-owner hashes are service
`163691d31a36134df3c6975e820d759fd1734a367ae93e33005f2e8247444644`, route
`b8f6fa7b6c8a3469160a8b1699cd87d4af20ddc2b35d0bbbb5cd075d506c9c48`, dependencies
`5567bdbd5fdc0b0f7181b9ee1a989b027e4991811afb2f79b744821f91cbdac7`, and owner
`e91aecf229c19e18f98696e2abced0ab9605191d7d8aa54fe6cfa3e0e74a7ba8`. Those hashes remain the
immutable historical S11A evidence and are never rebaselined.

The exact Accepted S9J successor-correction receipt is
`.agents/runs/rebuild-canonical-v2-knowledge-platform/s9j/verification-receipt.json` at raw-byte
SHA-256 `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`. It authorizes the
current corrected chat service
`15385247c9cf780e189651c97d15a9ad91fb6a5f8ef5f201bebcc19bb2814b82`, corrected S11A owner
`71e04271b9c6ef867795fba0ca3f9427ef418a8b5f736a952f9594130088a06a`, built-in chat page
`657c7d68c22e19ec1fd9470531dd0a71ed2b6587224d648fc842ea6223da463a`, and affected S11B owner
`21e7a68fe7699fd3a4295f87479f060cb2e05de326cf274d6dc9dbae57437f47`. The S11A route and
dependency-module hashes remain the historical Accepted values. This explicit successor chain is
not a silent S11A rebaseline.

S11B closes no OpenSpec task. It supplies the remaining implementation evidence for Tasks `11.1`
and `11.3`, plus focused interface and migration evidence for `11.2` and `11.4`. S11C retains the
aggregate repository verification, retired-test disposition, confirmation that no accepted behavior
depends on legacy details, and closure of Tasks `11.1`-`11.5`. The formal ledger therefore has no
S11B delta.

## Current registered admin and UI inventory

### Backend route groups

The current `apps/admin-console/backend/main.py` imports and registers every legacy router and
starts the V042 seed cron. Except for the S11A chat owner and the future S10O Canonical V2 operations
router, all registered groups below are coupled to the old physical model:

| Current entry point | Current effect | S11B disposition |
| --- | --- | --- |
| `GET /api/dashboard` in `api/dashboard.py` | Direct counts from V042 domain, pipeline, issue, and quality columns | Replace with release/manifest/projection/gap summary from one explicit V2 runtime |
| `/api/{professor,company,paper,patent}` in `api/domains.py` | Direct list/detail/filter/related SQL and direct PATCH/DELETE | Replace reads with typed release projections; remove direct edit/delete from candidate app |
| `/api/admin/professor/*` in `api/admin_professors.py` | V042 Professor detail plus direct admin-action/quality writes | Quarantine; provenance/detail comes from V2 projection/gap views |
| `/api/export/*` and hidden `/api/data/facets/*` | V042 SQL exports/facets | Replace export/facets from bounded typed V2 projection records |
| `/api/review/*` and `/api/pipeline-issues/*` | Mutable legacy `pipeline_issue` records and arbitrary evidence JSON | Quarantine; React operator view consumes Accepted S10O gaps |
| `/api/upload/*` | Writes legacy source/pipeline/domain rows and launches legacy subprocesses | Replace with offline `EvidenceLanding.ingest`; no browser direct-to-canonical write |
| `/api/batch/*` | Direct global `quality_status` mutation and deletes | Remove from candidate app; no V2 equivalent because path eligibility is versioned and release-scoped |
| `/api/pipeline/*` | V042 pipeline rows plus direct enrichment, Milvus backfill, and retrieval-validation subprocesses | Quarantine; candidate building/verification remains offline and explicit-target |
| `/api/seeds/*` plus `seed_cron.py` | Mutable legacy seed registry and Professor pipeline trigger | Quarantine; only an exact accepted S2B restore member may enter the S11B landing CLI |
| `POST /api/chat` | S11A migrates this route to the V2 adapter | Retain unchanged from Accepted S11A |
| `POST /api/chat/feedback` | Currently trusts client answer JSON and inserts `pipeline_issue` | Bind the S11A server checkpoint and record a typed S10O gap instead |
| `POST /api/chat/session/reset` | Issues an opaque cookie | Retain unchanged from Accepted S11A |
| `GET /api/canonical-v2/operations/gaps*` | S10O typed gap list/detail | Retain unchanged from Accepted S10O |

The candidate application must enumerate no other data/admin writer route. An uninstalled V2
runtime returns a stable `503`; it does not register or fall back to a legacy router.

The exact candidate route policy is finite. FastAPI framework documentation routes are disabled
with `openapi_url=None`, `docs_url=None`, and `redoc_url=None`. The known API set is exactly health;
S11A chat, feedback, and session reset; S10O gap list/detail; and the six S11B read-only admin
routes. The built-in pages are same-origin, so the candidate removes the legacy global permissive
`CORSMiddleware`; an unknown CORS preflight cannot bypass routing with a successful response. The
only additional `/api` route is a reject-only `/api/{path:path}` sink registered after
all known API routes and before static routes for `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`,
and `DELETE`; every invocation returns the same typed `404` and performs no dependency resolution or
effect. Outside `/api`, the allowed built-in surface is exactly `GET /`, `GET /browse`, `GET /chat`,
and the `/static` mount. The route owner treats the reject-only sink and those static routes as
explicit allowlist entries, never as data writers.

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

### Built-in browser consumer and legacy React reference

The current React application exposes legacy dashboard/domain/pipeline/seed/write APIs. It is useful
as historical implementation evidence but expanding it into a second V2 UI is YAGNI for this slice.
S11B therefore freezes the React application, navigation, APIs, pages, and tests as
`reference_only`: the candidate app neither mounts nor imports them.

The Specified baseline for `apps/admin-console/frontend/src/**` is 22 files. Its deterministic
sorted path-plus-raw-file-SHA-256 inventory digest is
`99abf5922399cd8bf20990934fa251c2a246da300fd4af3af384e6a9478ead77`. Candidate evidence records
the same pre/post count and digest. The digest input is a UTF-8 compact JSON array of sorted
`{"path":...,"sha256":...}` objects with sorted object keys and no trailing LF. This is a
non-blocking Minor evidence hardening measure; React still receives no npm/Vitest/Vite acceptance
gate.

The candidate UI is the existing built-in `browse.html`, extended only enough to show release-bound
status, four read-only domain views, related evidence, gaps, and bounded unavailable states through
the V2 endpoints. It must not call `/api/data/*`, legacy `/api/{domain}`, or any mutation endpoint.
The existing static chat page may remain the S11A chat surface; no npm/Vitest/Vite gate is introduced.

## Current domain writer, retrieval, and script inventory

### Legacy write surfaces

The executable legacy writer graph is rooted in:

- `src/data_agents/canonical/*`;
- `company/canonical_import.py` and Company release/enrichment persistence paths;
- `professor/canonical_writer.py`, `paper/canonical_writer.py`,
  `patent/canonical_writer.py`, their release/quality promotion modules, and direct domain-table
  update helpers;
- `publish.py`, domain vectorizers, `paper/milvus_backfill.py`,
  `storage/milvus_collections.py`, and `storage/milvus_store.py`;
- high-risk scripts including `run_company_release_e2e.py`, `run_professor_release_e2e.py`,
  `run_paper_release_e2e.py`, `run_patent_release_e2e.py`, `run_quality_promote.py`,
  `run_paper_identity_scan.py`, `run_professor_publish_to_search.py`, and
  `run_milvus_backfill.py`; and
- admin subprocess launchers in `api/upload.py` and `api/pipeline.py`.

S11B does not rewrite these implementations into a second V2 builder. The one sanctioned offline
writer is a new thin CLI over the Accepted `create_postgres_evidence_landing(...).ingest(...)`
interface. In this slice, only an exact accepted S2B restore member may enter that CLI and an
explicit isolated candidate target; newly collected or otherwise staged files are outside its
authority. `KnowledgeBuild` remains the only canonical construction interface and S12 owns the
complete candidate build. No S11B command calls `promote`.

### Legacy retrieval and evaluation surfaces

The old retrieval graph is rooted in `service/retrieval.py`, `service/search_service.py`, fixed
collection-name helpers, `backend.deps.get_retrieval_service`, the unregistered legacy chat callable,
and scripts such as `run_cross_domain_search_e2e.py`, `run_retrieval_chat_acceptance.py`,
`run_professor_retrieval_top5_eval.py`, and `apps/admin-console/scripts/eval_recall.py`.

Several admin-console evaluation scripts call `/api/chat`, but many still default to the old
`miroflow_real` DSN/Milvus file or treat prose/golden answers as truth. They remain historical
diagnostics and are not S11B/S12 acceptance commands. S11B adds one small black-box smoke caller that
requires an explicit base URL and expected release ID and validates the V2
`release -> plan -> lanes -> evidence -> claims` trace. It never imports `backend.main`,
`RetrievalService`, a V042 table, or a Milvus client. Claim-level quality execution remains S12/S2C
work.

## Selected V2 consumer seams

### Explicit release-bound admin read service

Add one admin-console-private `CanonicalV2ConsumerRuntime` installed explicitly on FastAPI
application state. The candidate does not accept independently supplied manifest/projection/
relationship objects. Its composition boundary exact-revalidates the serviceable
`PublishedRelease`, an accepted same-release `ReleaseVerification`, the complete
`IsolatedReleaseBundle`, and the matching `IndexProjectionRequest`; it derives the manifest and
candidate projections from that request and relationship publication authority from the bundle:

```text
PublishedRelease + accepted ReleaseVerification
  + IsolatedReleaseBundle + matching IndexProjectionRequest
  + release-bound planner/KnowledgeRead + KnowledgeAnswer factory
  + one PostgresKnowledgeGapOperations
  -> one controlled planner + S11A chat adapter + S11B admin runtime
  -> bounded dashboard/domain/detail/facet/export/related/gap-feedback results
```

The runtime rejects a loose `BuildManifest`, `CandidateProjectionResult`, or
`RelationshipProjectionResult` supplied outside the verified bundle/request graph. It requires the
accepted verification evidence IDs to equal the published release evidence IDs, validates one
release across every input at construction and before each returned result, and installs its chat,
admin, and gap-operation members as one identity-consistent aggregate. Object search/list, detail,
and relationship exploration execute an accepted typed plan through Accepted
`KnowledgeRead.execute`; the derived exact typed public-domain/relationship projections validate
identity, release, facets, export rows, and returned lineage. It never reconstructs V042 SQL or
exposes lane adapters. Gaps come only from the one Accepted S10O instance. Professor, Company,
Paper, and Patent remain the only public domains.

The app-state gap seam is explicit without changing Accepted S10O's dependency symbol. Preserve and
export the exact zero-argument `get_knowledge_gap_operations()` and its `_compose_operations()`
environment/`lru_cache` implementation so the direct S10O owner remains unchanged. Add the distinct
request dependency `get_canonical_v2_gap_operations(request: Request)`, which resolves only
`request.app.state.canonical_v2_consumer_runtime.gap_operations`. Candidate app construction sets
exactly
`app.dependency_overrides[get_knowledge_gap_operations] = get_canonical_v2_gap_operations`.
Accepted `get_canonical_v2_chat_adapter(request: Request)` remains unchanged and reads direct app
state for the predecessor shell. S11B adds
`get_canonical_v2_candidate_chat_adapter(request: Request)`, which reads only the aggregate chat
member, and candidate construction overrides the Accepted getter with it. The S11B admin getter also
resolves the aggregate. Missing/wrong aggregate state or a gap/chat/admin cross-wire returns the stable typed
`canonical_v2_runtime_unavailable` `503` before environment, SQL, provider, or source access. The
existing pre-S11B direct chat-app-state seam and zero-arg S10O environment composer remain solely for
frozen predecessor owners; the candidate request graph cannot reach either. A boundary owner makes
the zero-arg composer raise while the overridden candidate gap route still succeeds with the exact
aggregate identity; a valid direct-state chat adapter plus missing/wrong aggregate still makes the
candidate chat dependency return `503`.

`backend.main` owns V2-only `_create_canonical_v2_route_shell()` and
`create_canonical_v2_candidate_app(*, runtime)`. Module
`app = _create_canonical_v2_route_shell()` has no aggregate or dependency overrides and preserves
the exact S11A/S10O predecessor owners. The candidate factory always creates a fresh shell, installs
the exact aggregate, and installs exactly the chat and gap overrides above. S11B HTTP/smoke/import
evidence uses the factory, never module `app`; S12 owns the final installed entrypoint.

Aggregate construction treats only four exact typed artifacts as inspectable release authority:
`PublishedRelease`, `ReleaseVerification`, `IsolatedReleaseBundle`, and `IndexProjectionRequest`.
It rejects subclasses, hostile same-class/model-constructed values, and failed exact JSON
round-trips before touching an opaque port. It recomputes `BuildManifest.manifest_sha256` from
canonical JSON excluding `manifest_sha256`; requires `verification.accepted`, exact
`candidate_release_id == release_id`, exact verification/manifest SHA, and exact sorted verification
evidence IDs; replays `compose_candidate_projections(candidate_projection_request)` equal to the
supplied candidate result; requires the relationship request/result to be non-null, come only from
the bundle, and bind the same internal-reference request/result pair; replays
`create_ephemeral_index_projection_builder().build(index_projection_request)` equal to
`bundle.index_result`; and requires the candidate result's exact seven published manifests to equal
the bundle manifest's seven published manifests. Wrong type, hostile same-class content, forged
manifest hash, cross-release identity, missing/drifted relationship authority, replay drift, or a
fifth public domain fails with zero planner/read/answer/gap calls.

Planner, `KnowledgeRead`, answer factory/session, and gap operations remain opaque ports: construction
does not introspect or call them. Per call, a plan is exact-revalidated and its
`PlanningReleaseBinding` must match the aggregate-derived release ID, publication state/hash and
verification evidence IDs, manifest SHA, index request hash, index result hash, candidate result
hash, and internal-reference result hash before `KnowledgeRead.execute`. A typed plan/binding
mismatch therefore has `plan=1, read=answer=response=commit=0`. Post-read, `EvidenceSet` has only a
release ID, so its exact-model round-trip, query/release continuity, closed trace/evidence IDs, and
available typed receipt invariants are validated before answer or HTTP response
(`plan=read=1, answer=response=commit=0` on mismatch). Answer release/claim/evidence mismatch fails
before the copy-on-write session commit. Feedback obtains the immutable checkpoint first; absent or
cross-release checkpoint fails before `gap_operations.record`. Focused counters freeze each order.

S11A exposed two caller-owned controls that its accepted owner currently applies only in test
composition. S11B closes that gap in production composition: every real plan is exact-revalidated
with one explicitly supplied server-owned `SupplementalBudget`, and a representative
`EnumerationPolicy` is added only for the already-typed `company_has_patent/company_to_patent`
Company→Patent path with a non-empty displayed Company canonical-ID set. Its exact scope is
`representative Patents naming one displayed Company as applicant`. This is the only
runtime-authored replacement: the other three Accepted public relationship paths preserve their
incoming planner-owned policies exactly, as required by Accepted S8R3/S8R4/S8R5, while
non-enumeration plans with no incoming policy remain without one. There is no query-wording
inference and no mutation of an Accepted planner algorithm. The S11B observable candidate fixture
binds the exact accepted-owner budget `{max_wall_time_ms: 1000, max_provider_calls: 2,
max_retries: 1, max_cost_units: 5.0}` and records the resulting plan controls. S12 owns the final
candidate's explicit configuration and installation of the same composition boundary; neither
control may remain test-only or be omitted silently.

The bounded admin input contract is finite rather than model-introspected at request time:

- `domain` is exactly `company|paper|patent|professor`; canonical IDs and filter values are 1..200
  UTF-8 characters, and optional `q` is trimmed and at most 200 characters.
- List accepts at most four exact `(filter_field, filter_value)` pairs, `order=asc|desc`,
  `limit=1..100` (default 25), and `offset=0..10000`, with `offset + limit <= 10000`.
- Company filter/facet fields are `industry`, `geography`, and `quality_status`; NamedReference
  values match by exact `reference_id`; sort keys are
  `name`, `founded_at`, and `last_updated`.
- Paper filter/facet fields are `venue`, `year`, and `quality_status`; venue matches by exact
  NamedReference `reference_id`, year is a typed integer in `1000..9999`, and sort keys are `title`,
  `year`, `citation_count`, and `last_updated`.
- Patent filter/facet fields are `patent_type`, `publication_date`, and `quality_status`;
  `publication_date` is an exact typed ISO `YYYY-MM-DD` date, and sort keys are `title`,
  `publication_date`, `filing_date`, and `last_updated`.
- Professor filter/facet fields are `institution`, `department`, and `quality_status`; department
  matches by exact NamedReference `reference_id`; sort keys are `name`, `h_index`, `citation_count`,
  and `last_updated`.
- `founded_at`, `publication_date`, and `filing_date` sort as typed dates, `year` as a typed integer,
  and every primary sort uses `canonical_identity_id ASC` as its final deterministic tie-break,
  regardless of primary direction.
- A facet returns at most 100 buckets, ordered by descending count then normalized display value.
  Related traversal accepts `company_has_patent` for company↔patent and
  `professor_authored_paper` for professor↔paper only, with direction derived from the source
  domain and `limit=1..50` (default 20).
- Export requires 1..500 unique accepted canonical IDs and exactly `format=jsonl`; each line is the
  canonical typed projection JSON, with no alternate format, unbounded, or implicit "all rows" export.
  Unknown/mismatched keys, partial filter pairs, duplicate
  IDs, fifth domains, and unsupported relation/domain directions fail with typed `422` before a
  plan/read effect.

The service is read-only with respect to canonical, published, and index state. Its only write is a
typed user-feedback gap recorded through S10O from
`CanonicalV2ChatAdapter.get_feedback_checkpoint(session_id)`. The immutable
`ChatFeedbackCheckpoint` supplies the server-retained trace/evidence/release lineage. Client-supplied
answer text, citation JSON, release IDs, and evidence IDs are display context only and are never
trusted as gap lineage; no consumer receives a checkpoint setter or private-map access.

### Explicit offline evidence-ingest CLI

The CLI accepts exact `IngestEvidenceRequest` metadata plus one already-verified S2B restore member.
It requires all of:

```text
--database-url
--expected-database
--target-kind isolated-candidate|disposable
--backup-gate-root
--request-json
--source-id
--member-namespace
--member-relative-path
```

Its effect order is fixed: validate flags/request metadata without opening content; resolve the
explicit target and pass S2B gate/connect checks by calling
`create_postgres_evidence_landing(...)` exactly once and retaining that adapter; content-bind the
accepted S2B backup manifest, restore verification, and acceptance record; select exactly one
member-manifest row by `(source_id, namespace, relative_path)`; require request `source_locator` to
equal exactly `s2b-restore://{accepted_run_id}/{namespace}/{relative_path}`; derive its path only as
`restore_root / namespace / relative_path`; require the matching restore source row to be `passed`
and `hash_verified=true`/`copy_independent=true`; then `lstat` and require the current regular-file
size to equal the member row and the restore inode/device pair to differ from the recorded original,
backup object, and member-manifest files. Reject symlink/non-regular/original/backup/object/alias
escape, read that restore member exactly once, and require the current SHA-256 to match both the S2B
member hash and request `expected_content_sha256`; construct the real request from the validated
metadata plus those same bytes; call the retained adapter's `EvidenceLanding.ingest` exactly once;
and print the exact `LandingReceipt` JSON. The request JSON is a CLI-local metadata shape containing
every applicable `IngestEvidenceRequest` field except `content`; it rejects a caller-supplied
`content` key and requires non-null `expected_content_sha256`. An arbitrary `--content-file`, any
newly collected/staged file, an original/backup object, or a path absent from the accepted S2B
member manifest is forbidden. The CLI cannot open original sources as a write target, update V042
tables, build an active index, call
`KnowledgeBuild` internals, or promote a release.

### Machine-enforced quarantine inventory

Add a versioned JSON inventory and one static/runtime boundary owner. Its acceptance receipt freezes
the exact inventory SHA-256, category counts, disposition counts, and exact list/count of every
`s11c_disposition` entry. That immutable base count is not rewritten to zero. S11C may close Tasks
11.1-11.5 only after its separate overlay covers every frozen entry exactly once, leaves zero
unresolved overlay entries, and records every retired-test disposition. The inventory classifies:

- retired registered routers and React routes;
- legacy writer/retrieval/index modules;
- executable scripts that import those modules or target V001-V042 tables/fixed collections;
- legacy prose-gold evaluation scripts; and
- their sanctioned V2 replacement or `reference_only` disposition.

The owner discovers executable scripts and fails on an unclassified legacy dependency. It also
imports/enumerates the candidate app and sanctioned CLI, proving neither dependency graph reaches a
quarantined module or command. This is a bounded quarantine, not a broad source deletion. S11C may
later delete retired files only after aggregate checks prove no accepted behavior depends on them.

The Specified pre-S11B discovery universe is exactly 140 executable script inputs: 116 Python files
and 24 shell files under the two application `scripts/` trees. The sorted path-list SHA-256 is
`9235ceaf2bade6ae5012dc2db74d7ab5c994ba0151ea7cf40c602bfcdd0aa654`; the sorted
path-plus-raw-file-SHA-256 inventory digest is
`9512e595fc49d9b3b7d2cce789d72b2ea4e8421e1c4e8b5d34de7541bc3569d3`. Candidate discovery must
account for those 140 paths plus exactly the three new sanctioned Python CLIs, for 143 post-S11B
inputs: evidence ingest, candidate smoke, and deterministic baseline capture. The path-list digest
input is a UTF-8 compact JSON array of sorted paths; the path/hash digest input is a UTF-8 compact
JSON array of sorted `{"path":...,"sha256":...}` objects with sorted keys. Neither input has a
trailing LF. Python files are parsed
with AST-based import/call/body inspection. Shell files are scanned deterministically for
repository-relative command targets, legacy script/module names, generic target variables,
V001-V042/table markers, and fixed collection/index commands. Neither scanner executes a retired
entrypoint. Every matched legacy path is classified; every unmatched path remains visible in the
discovery receipt so a partial hand-maintained list cannot masquerade as exhaustive coverage.

The S11B verification receipt freezes the inventory authority at the exact JSON pointer
`/legacy_consumer_inventory/sha256`. Its `legacy_consumer_inventory` subtree contains exact fields
`path`, `sha256`, `category_counts`, `disposition_counts`, `s11c_disposition_entries`, and
`s11c_disposition_count`; `s11c_disposition_entries` is a lexicographically sorted array of exact
`{"inventory_category": <top-level category>, "inventory_path": <path-or-module>}` pairs plus its
count. A separate `broad_test_baseline.runs` subtree records each exact cwd, collection argv and
execution argv token array, exit code,
collected-nodeid artifact path/hash, JUnit artifact path/hash, and each failure/error's exact nodeid,
phase, outcome, and `normalized_failure_signature_sha256`; the exact run fields are `run_id`, `cwd`,
`collection_argv`, `argv`,
`exit_code`, `collected_nodeids_path`, `collected_nodeids_sha256`, `junit_xml_path`,
`junit_xml_sha256`, and `failures`. Signature normalization changes only CRLF to LF, the exact
run-mode `--basetemp` root to `<pytest-tmp>/` first, and the exact repository root to `<repo>/`
second, then
hashes `outcome + LF + normalized_message + LF + normalized_body`. Message/body come from the
persisted JUnit failure/error element so S11C can independently recompute every signature; the
ephemeral report hook supplies exact nodeid/phase/outcome and lifecycle bijection only. Phase is stored separately and
must remain in exact JUnit/report-hook bijection. S11C may use
`unrelated_preexisting` only for an exact baseline entry retained there; an absent entry makes that
disposition unavailable.

Inventory identity is canonical, not whatever spelling happens to appear in JSON. Every file
identity is a repository-relative POSIX path with exact case; absolute paths, backslashes, empty or
`.` segments, `..`, repeated separators, NULs, symlink aliases, and paths outside the repository are
rejected. Every module identity is a dot-separated sequence of Python identifiers. An entry has
exactly one of `path` or `module`; its canonical identity is prefixed `path:` or `module:`. Entries
are sorted by canonical identity inside each fixed top-level category and no canonical identity may
appear twice or in both retired and sanctioned sets. The loader reserializes with UTF-8,
`ensure_ascii=False`, sorted object keys, compact separators, `allow_nan=False`, and exactly one
trailing LF, rejects non-canonical source bytes, and hashes those canonical raw bytes. Discovery and
the S11C `(category, identity)` handoff use the same canonicalizer, so aliases or reordered JSON
cannot create a second inventory identity or a silent rebaseline.

Broad-baseline evidence is produced only by the deterministic sanctioned
`capture_canonical_v2_s11b_baseline.py`; a human-written receipt is not a producer. The producer has
a fixed run-ID-to-argv table, writes collected node IDs and JUnit XML under the S11B baseline
directory, parses both outputs, applies the frozen signature normalization, and emits the receipt
subtree plus a guard/preflight receipt. Before collection it sets `PYTHON_DOTENV_DISABLED=1` and
holds every member of the Slice Contract's literal sorted 49-name `SENSITIVE_ENV_NAMES` tuple
present-empty; the receipt array must equal `list(SENSITIVE_ENV_NAMES)` exactly. Socket guard v2
permits AF_INET `connect` only to numeric `127.0.0.1:<exact port>` when the matching socket object
in the same child called patched `listen` after guard installation, is still live, and has
`SO_ACCEPTCONN=1`. This exception exists solely for the required black-box candidate smoke test.
AF_INET6, unowned/closed/wrong-port/non-loopback AF_INET, every inet `connect_ex`, and every psycopg
connection remain fail-closed. AF_UNIX remains permitted only under an exact producer-owned
temporary root. Before child startup it
creates that root as a fresh `0700` `/tmp/s11b-*` directory—not ambient `/tmp` itself—and verifies
the encoded `guard-probe.sock` path does not exceed Linux's 107-byte AF_UNIX limit. It binds
`TMPDIR`, `TMP`, `TEMP`, the child-stage paths, and the intended pytest temp root beneath that root.
The early plugin installs guards in `pytest_load_initial_conftests`; its `tryfirst`
`pytest_configure` replaces `config.option.basetemp` with
`CANONICAL_V2_S11B_PYTEST_TEMP` and, in run mode, replaces `config.option.xmlpath` with
`CANONICAL_V2_S11B_JUNIT_STAGE` before collection, fixture, or JUnit write effects, so Milvus Lite's
temporary socket cannot escape to ambient `/tmp`. A wrapper may call the original
`dotenv.load_dotenv`, but
captures mutations and, in `finally`, restores all 49 members to their exact pre-call present-empty
state before recording or raising. Preflight proves a no-op; mutation RED proves the expected guard
error and all 49 values still equal `""` afterward. This includes all four
`CANONICAL_V2_TEST_*` integration gates; a separately authorized disposable-database acceptance run
is outside B6 and is the only place they may be populated jointly.
The admin partition uses the explicit pytest marker expression
`-m "not requires_classifier_llm"`, never `-k`, and records the unique deselected node
`tests/test_classifier_benchmark.py::test_classifier_benchmark`.
No `-k`, known-failure selection, xfail, skip injection, or node-ID omission is allowed; explicit
external-marker exclusion is the sole suite filter and is recorded in argv and collection evidence.
Child receipts use `canonical-v2-s11b-child-guard-v3`, JUnit-recomputable baseline signature v3,
socket guard v2, and
`attempt_attribution=pytest-current-test-report-v1`. The child environment removes inherited
`PYTEST_CURRENT_TEST` and restores every sensitive name to present-empty at session finish before
the session-finish receipt update, including proxy names intentionally deleted by legacy tests. One process-local
`threading.RLock` serializes every guard-state mutation with its receipt snapshot and write, so
concurrent worker attempts remain complete, valid JSON evidence with duplicates preserved. The
dedicated child never restores the patched socket/psycopg/dotenv guards during
`pytest_unconfigure`; they and the live guard state remain installed through process exit, including
late workers and `atexit` callbacks. Any such unattributed late attempt is physically blocked,
recorded in `forbidden_attempts`, and causes the parent to reject the run. Only the bytes read by the
parent after the subprocess has fully exited are the terminal child receipt. A non-probe socket/psycopg attempt enters `blocked_test_attempts` only after
the guard blocks it before effect in an exact active run-mode `call` context, including a worker
thread spawned during that call. The parent requires
collected membership, one exact report row/outcome, and exitstatus/subprocess agreement; top-level
rows add run ID/outcome, retain duplicates, and publish an exact count. `forbidden_attempts` remains
empty. Collection-time, setup/teardown, post-call worker, unattributed, unsupported, or unreported
attempts fail closed; collection also permits no blocked-test or owned-loopback rows. If preflight/
guard installation fails, collection differs from the recorded partition, or pytest is
interrupted, the producer exits non-zero and emits no baseline run. The earlier dotenv-restored
real-DSN attempt was unsafe and aborted and can never be used as a baseline.
Top-level guard evidence records `pytest_temp_roots` as an exact run-id mapping with separate
`collect` and `run` roots. The old singular `pytest_temp_root` field is forbidden; every child
receipt independently repeats its exact root, and signature normalization uses only the matching
run-mode root.

The fixed `canonical-v2-no-external` partition has cwd `apps/miroflow-agent` and argv
`["uv","run","pytest","-o","addopts=","-p","no:cacheprovider","-q","--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/tmp/canonical-v2-no-external/pytest","--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/canonical-v2-no-external.xml","tests/canonical_v2"]`.
The fixed `admin-no-external` partition has cwd `apps/admin-console` and argv
`["uv","run","pytest","-o","addopts=","-p","no:cacheprovider","-q","-m","not requires_classifier_llm","--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/tmp/admin-no-external/pytest","--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/admin-no-external.xml","tests"]`.
The literal basetemp/JUnit values in both argv arrays are frozen audit sentinel tokens, not write
destinations. The early plugin must perform the exact option rebinding above; collect mode disables
JUnit output. Missing or late rebinding invalidates the guard receipt and the run.
Each collection argv removes its JUnit token and inserts `--collect-only` immediately before the
test path. Nodeid files are UTF-8, lexicographically sorted unique, one exact LF-terminated nodeid per line,
with no summary. Each collected nodeid maps through pytest's exact JUnit address mangling to one
unique `(classname,name)` testcase and every testcase maps back to that nodeid; positional matching
is forbidden. Each executed nodeid has one setup and teardown report, plus exactly one call report
iff setup passed, with no duplicate phase. The derived terminal `passed|skipped|failure|error`
outcome must equal the JUnit child outcome. Every failure/error annotation must belong to its parent
testcase and match one exact identity/lifecycle report row; missing, duplicate, ambiguous, or mismatched
JUnit/report-hook/nodeid evidence fails closed.
Collection must exit exactly `0`; a run may exit only `0` (no test failures) or `1` (recorded test
failures). Pytest interruption/internal-error/usage/no-tests codes `2|3|4|5` and signal exits are
ineligible even when the child receipt agrees with the subprocess.

Each run starts with a fresh exclusive child stage beneath `/tmp/s11b-*` and a distinct parent-only
stage on the output filesystem, and rejects a pre-existing stage, final nodeid/JUnit target, or
baseline row. The child writes only beneath the owned `/tmp` stage/temp tree, completes parsing and
the exact
nodeid/JUnit/report-hook bijection, then copies validated child artifacts into a parent-only stage
on the output filesystem, verifies byte-identical SHA-256, and uses same-filesystem hard links to
promote without overwrite; the baseline row is exposed last. A `finally` block terminates only
owned child processes and removes
the unpromoted stage and owned `TMPDIR`/`TMP`/`TEMP`/`--basetemp` tree on success, failure, and
interruption. Any failure
removes all newly promoted nodeid/JUnit artifacts and emits no row while preserving pre-existing
outputs. Accepted evidence requires `cleanup=true` and zero live owned children/stage/temp roots.

## Migration and quarantine mapping

| Legacy behavior | Canonical V2 owner | S11B action |
| --- | --- | --- |
| Domain SQL list/detail/filter/export | `KnowledgeRead.execute` plus exact typed projections bound to `PublishedRelease` | New read-only admin service/API and built-in `browse.html` mapping |
| Related-object SQL/retrieval helper | release-bound `KnowledgeRead.execute` / exact relationship authority | New typed related receipt with release and evidence lineage |
| Chat HTTP planning/retrieval/answer | Accepted S11A | Consume unchanged; no second adapter |
| Chat/user quality report | Accepted S10O gap operations + S11A server checkpoint | Record typed gap; ignore client-authored lineage |
| Admin issue/review rows | Accepted S10O list/detail and offline remediation | Replace UI with V2 gap view; unregister legacy issue routers |
| Upload/collector direct canonical writes | `EvidenceLanding.ingest` | New explicit-target CLI; unregister browser upload writer |
| Domain merge/quality/lifecycle mutation | offline `KnowledgeBuild` assertions/decisions/policies | Quarantine direct PATCH/DELETE/batch actions; no online replacement |
| Direct Milvus backfill/publish/alias mutation | candidate index build plus `ReleasePublication.verify` | Quarantine commands/endpoints; S12 builds/verifies isolated candidate |
| Fixed-handler/legacy `RetrievalService` callers | S11A or `KnowledgeRead.execute` | No accepted imports; one black-box V2 smoke caller |
| Global `ready`/`quality_status` serving gate | domain inclusion plus path eligibility/limitations | Render V2 typed quality/limitations without mutating a global gate |
| Old collection names and `MILVUS_URI` defaults | exact release/index manifests and target markers | Forbidden from accepted app/CLI dependency graphs |

## Compatibility boundary

- `POST /api/chat`, its request fields, response envelope, cookie, and exact option-binding behavior
  remain owned by S11A and unchanged by S11B.
- The candidate entry point imports S11A's V2-only router/contracts/dependency seam directly and
  never imports `backend.api.chat` or `backend.deps`. Those legacy modules remain comparison-only.
- `browse.html` and admin endpoints are the minimal pre-launch consumer. S11B may introduce
  `/api/canonical-v2/admin/*` endpoints and typed V2 response models rather than preserve V042
  physical IDs, legacy quality flags, pipeline stages, or mutation semantics. Legacy React is
  `reference_only`, unmounted, and unimported.
- The four public domain names remain stable. Domain object IDs become accepted Canonical V2 IDs,
  every response identifies `release_id`, and evidence/projection lineage remains visible.
- Read-only display fields may retain familiar labels in `browse.html`, but absence/limitation is rendered
  honestly. No compatibility mapper invents a field that is absent from the typed projection.
- Old mutation URLs are unregistered in the candidate application. They do not silently translate a
  destructive edit into a different operation. The V2 UI exposes read-only data plus gaps and
  offline-remediation status.
- Legacy scripts, response prose, table order, collection names, V042 IDs, and global readiness are
  not public compatibility contracts.
- Static `GET /api/canonical-v2/admin/domains/{domain}/export` is registered before dynamic
  `GET /api/canonical-v2/admin/domains/{domain}/{canonical_id}` so `export` cannot be captured as an
  object ID. The exact seven-method unknown `/api/{path:path}` sink returns the typed `404` before
  any static route; no unknown API request receives `405`, HTML, or a successful SPA fallback.

## Explicit target and no-cutover boundary

The candidate admin runtime receives already-validated typed release objects through explicit app
state. It does not discover `DATABASE_URL`, `DATABASE_URL_TEST`, `MILVUS_URI`,
`CHAT_MILVUS_URI`, a fixed collection, an active alias, or a latest release.

The evidence-ingest CLI requires a target identity and accepted backup gate. Only an exact
`isolated-candidate` or `disposable` database may be used. Any generic DSN fallback, original
`pgtest`, original Milvus path/hash, production-like target, missing expected database identity, or
ambiguous target kind or protected/unsafe path fails before opening content or writing. Only an
exact accepted S2B restore member is read, exactly once after the gate, unique-row, locator, status,
size, path, and inode-independence checks; the same bytes are hashed and ingested. The CLI has no
promotion operation.

S11B does not alter `publish.active_release`, any Milvus alias/pointer, original source bytes,
forensic artifacts, or remote Git state. S12 owns complete candidate composition and final isolated
installation. Task 12.6 and separate user authorization own any production-like Cutover.

## OpenSpec task mapping

- **Task 11.1:** S11B implements the remaining admin/API/UI, sanctioned offline writer, and
  sanctioned retrieval/script subsets after S11A. S11C retains aggregate confirmation and checkbox
  closure.
- **Task 11.2:** S11B adds public-interface, candidate-app, CLI, built-in UI, and quarantine owners.
  S11C retains broad replacement/retired-test disposition and claim-contract regression execution.
- **Task 11.3:** S11B unregisters and machine-quarantines V042 writers, direct SQL admin paths,
  legacy retrieval/fixed-handler imports, global readiness, old collection assumptions, and direct
  active-index commands. S11C confirms there are no remaining accepted dependencies.
- **Task 11.4:** S11B runs targeted and proportional candidate/disposable checks only. S11C owns the
  broad repository check and unrelated/retired failure ledger.
- **Task 11.5:** S11B may become Accepted as a dependency checkpoint, but aggregate consumer review
  and OpenSpec task closure remain S11C.

No task is checked by S11B. Record the live ledger before and after acceptance with no delta.

## Options considered

1. **One explicit V2 candidate app plus a machine quarantine boundary — selected.** This makes the
   running consumer graph unambiguous without deleting historical code before aggregate review.
2. Rewrite every V042 route, domain writer, and script in place. This would preserve obsolete
   physical semantics, duplicate `KnowledgeBuild`, and create a large unreviewable slice.
3. Keep old and V2 routes behind per-request feature flags. This permits silent fallback and makes
   it impossible to prove which storage/index contract served a result.
4. Delete every legacy module immediately. This would mix migration with broad cleanup and make
   valid historical tests/evidence harder to classify before S11C.

## Ready and acceptance decision

The Admin RED/GREEN owner runs with `--noconftest` on every focused command. Its module top level is
limited to the standard library, pytest, and the `TestClient` type; it uses only built-in
`request`/`tmp_path`/`monkeypatch` fixtures and completes its dynamic seam loader before importing
`backend.main` or constructing a client. Normal, forced, and GREEN argv are the exact commands in
the plan. This exception is focused-owner-only: broad Admin baseline retains normal conftest.

The boundary owner's strict xfail covers one complete DAG, not only inventory. It remains until the
inventory/loader and all three sanctioned CLIs (evidence ingest, candidate smoke, baseline capture)
plus their focused owners are complete; only then may its exact nodeid become GREEN.

The historical resume-to-Candidate gate required:

- S10O, historical S11A, and S9J Slice Contracts and final receipts all say Accepted;
- this audit, plan, and Slice Contract receive one lean review with zero open Critical/Important;
- the V2-only import quarantine, read-only feedback checkpoint, CLI-local metadata and retained
  gate/connect-checked landing adapter, complete Python/shell discovery, exact route/static/docs/CORS
  policy, exact aggregate gap override, replayed four-artifact graph, opaque-port effect order,
  seven-method unknown-API `404`, static-export ordering, minimal `browse.html` UI,
  and exact S11C inventory/baseline receipt fields are frozen in all three artifacts;
- strict OpenSpec and document/scope checks pass; and
- reviewed current In Progress dependency hashes and a UTC timestamp are recorded before focused
  GREEN and broad baseline evidence is promoted to Candidate evidence.

S11B acceptance requires a release-bound admin/API/built-in-UI observable demo, typed chat-feedback
gap, explicit-target landing CLI proof, candidate-app router/import quarantine proof, focused static
UI checks, proportional no-external checks, and one lean implementation review with zero open Critical/
Important. Minor/YAGNI findings are recorded and non-blocking. Acceptance does not check Tasks
`11.1`-`11.5`, build a complete S12 candidate, promote a release, or authorize Commit, Push, PR,
Archive, destructive cleanup, or Cutover.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md` Decisions 0, 3, 5, 6, 11,
  and 12;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/canonical-v2-knowledge/spec.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/canonical-v2-release/spec.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/recovery-evidence-landing/spec.md`;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/knowledge-gap-feedback/spec.md`;
- Accepted S10O, historical S11A, and Accepted S9J contracts/receipts;
- `apps/admin-console/backend/main.py`, `backend/deps.py`, registered `backend/api/*`,
  `frontend/src/App.tsx`, `frontend/src/api.ts`, and current pages;
- `apps/miroflow-agent/src/data_agents/canonical_v2/*` deep-module interfaces;
- current legacy canonical/writer/retrieval/index modules and executable scripts as implementation
  evidence only.

This audit changed no production code, test, OpenSpec checkbox, acceptance artifact, existing slice,
database, index, source, provider, pointer, Commit, Push, PR, Archive, promotion, or Cutover.
