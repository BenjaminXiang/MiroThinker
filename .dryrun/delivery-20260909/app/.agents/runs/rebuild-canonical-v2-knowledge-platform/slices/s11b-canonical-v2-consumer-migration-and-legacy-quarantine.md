# Slice Contract: S11B Canonical V2 Consumer Migration and Legacy Quarantine

## Status

Accepted at `2026-07-21T12:54:16Z` after the final receipt/state review reported `Critical=0` and
`Important=0`. The earlier Candidate attempt at `2026-07-21T11:48:32Z` was rejected and its v2
baseline/receipt deleted after review found stale normalization tokens and a non-recomputable
ephemeral report-hook source. In Progress originally began at
`2026-07-21T10:00:31Z`; the historical Ready transition at
`2026-07-20T21:07:56Z` came from the authoritative reviewed Specified hashes audit
`d4ae8e61276a36b25ada278faab21c8b7034abd99b53a8ac3c1ee21e7b7e45da`, plan
`22856c4bbc3b28a7510770730f16d595a08b113d5e8d0dedd39e17acd961565f`, and contract
`e577ed82c95814304ff70555c5dc6dad97a79095734cdc8765a0db9b869f43c8`.

Review evidence recorded at `2026-07-20T21:07:56Z` is:

- runtime/composition review: `Critical=0/Important=0/Minor=2/YAGNI=0`, Ready=yes;
- guarded-baseline review: `Critical=0/Important=0/Minor=0/YAGNI=0`, Ready=yes; and
- executable RED/preflight review: `Critical=0/Important=0`, with exact focused command, dynamic
  seam ordering, predecessor-shell/candidate-factory compatibility, and three-CLI DAG checks closed.

The two runtime-review Minors are recorded and non-blocking: **M1** notes that the audit shorthand
“one release across every input at construction” is broader than the immediately following
normative four-artifact/opaque-port distinction; that normative text removes implementation
ambiguity. **M2** notes that “the dynamic seam loader completes before importing `backend.main`” is
literal shorthand: all non-main sentinels complete first, `backend.main` is imported last so its two
factory seams can be inspected, and the full loader completes before `TestClient`; the required seam
order is unambiguous. Per the Minor/YAGNI policy, neither note triggers another theory edit.

Accepted S10O receipt `e0cc1b031066b346e62582fd585ee15a30d7483a498b701b204605a242b92246`,
Accepted S11A receipt `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`,
and dependency module hash `5567bdbd5fdc0b0f7181b9ee1a989b027e4991811afb2f79b744821f91cbdac7`
were rechecked by the historical Ready review. Strict OpenSpec validation and `git diff --check`
passed on those reviewed Specified bytes. Current production, owner, inventory, CLI, and fresh
signature-v3 baseline bytes have focused GREEN, strict/static checks, and independent reviews with
zero open Critical/Important. Row
`a9bdfcdb5d2b8a6409811de6bf8c53bc66e7e2d78afa92edb9cc09cf0b06f668` binds 530 Canonical V2 and
596 Admin nodeids, exact 18 failure/4 setup-error signatures, 15 attributable blocked attempts,
zero forbidden attempts, complete cleanup, and 22/22 persisted-JUnit signature replays. The ledger
remains `65/80`; no OpenSpec task or acceptance checkbox changed. S11C remains Specified and owns
aggregate closure of Tasks `11.1`-`11.5`.

Accepted S9J receipt `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`
is the explicit successor authority for corrected chat service
`15385247c9cf780e189651c97d15a9ad91fb6a5f8ef5f201bebcc19bb2814b82`, corrected S11A owner
`71e04271b9c6ef867795fba0ca3f9427ef418a8b5f736a952f9594130088a06a`, and affected S11B owner
`21e7a68fe7699fd3a4295f87479f060cb2e05de326cf274d6dc9dbae57437f47`. Historical S11A receipt,
service, and owner hashes remain immutable evidence; this dependency sync is not a rebaseline.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`.
- Requirements:
  - `design.md` Decision 6 — consumers use the five deep modules rather than physical storage;
  - `design.md` Decisions 0 and 11 — explicit isolated targets and one release across canonical,
    serving projections, and indexes;
  - `specs/canonical-v2-knowledge/spec.md` — typed four-domain projections, retained provenance,
    path eligibility, and no query-time identity/canonical mutation;
  - `specs/canonical-v2-release/spec.md` — immutable candidate/release/index parity and explicit
    publication authority;
  - `specs/recovery-evidence-landing/spec.md` — immutable landing and no bypass to canonical;
  - `specs/knowledge-gap-feedback/spec.md` — typed admin/feedback gaps and offline accepted-release
    remediation.
- OpenSpec tasks: remaining implementation evidence for `11.1` and `11.3`; partial interface/check
  evidence for `11.2` and `11.4`; this slice checks none.
- Aggregate owner: S11C retains closure of Tasks `11.1`-`11.5` and Task `11.5` acceptance.
- Depends on: Accepted S10O, historical Accepted S11A, and Accepted S9J, including final receipt
  hashes.
- Exact historical S11A authority: final receipt SHA-256
  `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`; final service, route,
  dependency, and owner SHA-256 values
  `163691d31a36134df3c6975e820d759fd1734a367ae93e33005f2e8247444644`,
  `b8f6fa7b6c8a3469160a8b1699cd87d4af20ddc2b35d0bbbb5cd075d506c9c48`,
  `5567bdbd5fdc0b0f7181b9ee1a989b027e4991811afb2f79b744821f91cbdac7`, and
  `e91aecf229c19e18f98696e2abced0ab9605191d7d8aa54fe6cfa3e0e74a7ba8`.
- Exact S9J successor authority: receipt SHA-256
  `ae34240cde353a272faa23710bfdf3818763ac261891bf48bc5307048a8759bc`; corrected chat service,
  S11A owner, and S11B owner SHA-256 values
  `15385247c9cf780e189651c97d15a9ad91fb6a5f8ef5f201bebcc19bb2814b82`,
  `71e04271b9c6ef867795fba0ca3f9427ef418a8b5f736a952f9594130088a06a`, and
  `21e7a68fe7699fd3a4295f87479f060cb2e05de326cf274d6dc9dbae57437f47`.
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/dependency-audit.md`.
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/implementation-plan.md`.

## Goal

Make the observable candidate consumer graph exactly:

```text
candidate admin app
  -> Accepted S11A release-bound /api/chat
  -> Accepted S10O typed gap list/detail and feedback destination
  -> one explicit release-bound typed projection/read admin runtime

offline domain/source artifact
  -> one explicit isolated candidate target
  -> EvidenceLanding.ingest
  -> immutable LandingReceipt

black-box smoke query
  -> explicit candidate base URL + expected release
  -> /api/chat V2 release/plan/lanes/evidence/claims trace
```

No registered/imported/sanctioned path may reach V001-V042 serving tables, legacy canonical writers,
the legacy `RetrievalService` or fixed handler, global readiness, fixed collection names, direct
active-index mutation, an implicit database/index/release, or a legacy fallback. The candidate app
imports S11A only through its V2-only chat/contracts/dependency modules, never legacy
`backend.api.chat` or `backend.deps`.

## Required behavior

- One admin-console-private `CanonicalV2ConsumerRuntime` binds exactly one serviceable accepted
  `PublishedRelease`, accepted same-release `ReleaseVerification`, exact `IsolatedReleaseBundle`,
  matching `IndexProjectionRequest`, release-bound planner/`KnowledgeRead`, KnowledgeAnswer factory,
  and Accepted S10O operations object. It derives manifest/candidate projection data from the
  bundle/request and relationship publication authority from the bundle; loose independently
  supplied derivatives are rejected.
- Construction exact-model-round-trips the release inputs and requires exact verification/
  publication evidence-ID equality. Construction and every result validate one exact release.
  Manifest/projection/relationship/read/gap/chat cross-wire fails before the next downstream effect.
- Before any opaque-port call, construction requires exact non-subclass types and hostile
  same-class-safe JSON round-trips for the four artifacts; recomputes canonical manifest SHA
  excluding `manifest_sha256`; requires accepted verification with exact candidate release,
  release, manifest SHA, and sorted publication evidence IDs; requires exact
  `compose_candidate_projections(...)` replay; binds the bundle's non-null relationship pair to the
  candidate request's internal-reference pair; requires exact
  `create_ephemeral_index_projection_builder().build(...)` replay equal to `bundle.index_result`;
  and compares the candidate result's exact seven published manifests to the manifest's exact seven.
  Wrong type, hostile same-class/model construction, forged manifest, cross release, verification
  drift, missing/drifted relationship authority, replay drift, or fifth domain has zero port calls.
- The aggregate composes the one S11A chat adapter, one S11B admin runtime, controlled planner, and
  exact same S10O gap-operations identity. Candidate dependencies resolve only
  `request.app.state.canonical_v2_consumer_runtime`; missing/wrong aggregate or member, or an
  identity/release cross-wire, returns stable typed `canonical_v2_runtime_unavailable` `503` before
  environment, SQL, provider, source, or fallback access. The pre-S11B direct chat state and current
  environment/`lru_cache` S10O composition remain predecessor-only and are unreachable from the
  candidate app.
- Accepted S10O's exported zero-argument `get_knowledge_gap_operations()` and private
  `_compose_operations()` remain unchanged. S11B adds exactly
  `get_canonical_v2_gap_operations(request: Request)`, and candidate construction installs identity
  `app.dependency_overrides[get_knowledge_gap_operations] is get_canonical_v2_gap_operations`.
  The new getter alone resolves the aggregate gap member. Missing/wrong state returns the aggregate
  `503` with zero composer/storage effects. Even when `_compose_operations` raises, the overridden
  candidate route succeeds; the direct S10O owner remains unchanged.
- Accepted direct-state `get_canonical_v2_chat_adapter(request: Request)` remains unchanged for the
  predecessor shell. S11B adds aggregate-only
  `get_canonical_v2_candidate_chat_adapter(request: Request)`. `backend.main` defines V2-only
  `_create_canonical_v2_route_shell()` and
  `create_canonical_v2_candidate_app(*, runtime: CanonicalV2ConsumerRuntime)`: module `app` is a
  fresh route shell with no aggregate/overrides, while each candidate is a new shell with exact
  aggregate and exact overrides from Accepted chat getter to candidate chat getter and Accepted gap
  getter to candidate gap getter. S11B owner/smoke/import evidence uses the factory. A valid direct
  chat state plus missing/wrong aggregate still returns the aggregate `503`; S12 owns the installed
  entrypoint.
- Production composition exact-revalidates every real `RetrievalPlan` with an explicitly supplied
  server-owned `SupplementalBudget`. It binds a representative caller-owned `EnumerationPolicy`
  only when the plan already has exactly the typed `company_has_patent/company_to_patent`
  Company→Patent path and a non-empty displayed Company canonical-ID set. Its exact scope is
  `representative Patents naming one displayed Company as applicant`; it uses the exact plan
  `as_of`, `exhaustive=False`, and
  `continuation_state="available"`. This is the only runtime-authored enumeration-policy
  replacement. The other three Accepted public relationship paths preserve the incoming planner
  policy exactly, as required by Accepted S8R3/S8R4/S8R5; non-enumeration plans that arrive without
  a policy remain without one. It never infers from query wording or changes an Accepted planner
  algorithm. The demo budget is exactly `1000 ms / 2 provider calls / 1 retry / 5.0 cost units`;
  S12 owns final explicit values and installation through the same boundary. These controls SHALL
  NOT remain test-only.
- Professor, Company, Paper, and Patent are the only public domain populations. Internal Person/
  Technology evidence remains auxiliary and cannot be returned as a fifth public domain.
- Object search/list, detail, and related requests execute an accepted typed plan through the
  release-bound `KnowledgeRead.execute`. Exact typed projections validate returned identity/release
  and own deterministic status/facet/export data. Every result carries release/projection/as-of
  identity and retains evidence/field or relationship lineage and limitations.
- Planner/read/answer/gap dependencies are opaque ports and are neither type-introspected nor called
  during construction. Before `KnowledgeRead.execute`, exact plan validation compares
  `PlanningReleaseBinding` to aggregate-derived release/publication state and hash, verification
  evidence IDs, manifest SHA, index request/result hashes, candidate result hash, and
  internal-reference result hash, not only release ID. Post-read validation exact-round-trips the
  `EvidenceSet` and checks query/release continuity, closed evidence/trace references, and every
  available typed receipt before answer/response. Answer release/claim/evidence closure is checked
  before copy-on-write commit. Absent/cross-release feedback checkpoint is rejected before gap
  record. Exact counters own each stop order.
- Filters, sort keys, relation types, pagination, and export size use explicit typed allowlists.
  Arbitrary SQL, arbitrary JSON paths, caller-authored table/collection names, and unbounded export
  are rejected.
- The exact admin bounds are: domains `company|paper|patent|professor`; `q`, canonical IDs, and
  filter values 1..200 characters when present; at most four complete filter pairs;
  `order=asc|desc`; list `limit=1..100` default 25; `offset=0..10000` with
  `offset+limit<=10000`; facet output at most 100 buckets ordered by descending count then normalized
  display value; related `limit=1..50` default 20; export 1..500 unique accepted IDs and only
  `format=jsonl`, with no alternate format or implicit all; each line is canonical typed projection JSON.
- Exact Company filter/facet fields are `industry|geography|quality_status`, with sorts
  `name|founded_at|last_updated`, and NamedReference values match exact `reference_id`; Paper fields
  are `venue|year|quality_status`, venue matches exact `reference_id`, year is typed `1000..9999`, with sorts
  `title|year|citation_count|last_updated`; Patent fields are
  `patent_type|publication_date|quality_status`, with sorts
  `title|publication_date|filing_date|last_updated`; Professor fields are
  `institution|department|quality_status`, department matches exact `reference_id`, with sorts
  `name|h_index|citation_count|last_updated`. Year/date values are typed and every sort ends with
  `canonical_identity_id ASC` regardless of primary direction. Related permits only `company_has_patent` for
  company↔patent and `professor_authored_paper` for professor↔paper, deriving direction from the
  source domain. Unknown/mismatched/partial inputs fail typed `422` before planning or reading.
- Related retrieval uses Accepted release-bound `KnowledgeRead.execute` and exact relationship
  publication authority from the same release. It does not call a legacy retrieval/search service,
  direct relationship SQL, or a caller-provided lane adapter.
- The admin runtime performs no canonical, identity, assertion, decision, release, pointer, or index
  mutation. It does not expose direct edit/delete, batch quality, upload-to-canonical, build,
  promotion, alias, or raw SQL endpoints.
- `POST /api/chat` and session reset retain Accepted S11A behavior exactly. S11B does not add another
  planner/read/answer/session adapter.
- Chat feedback calls `CanonicalV2ChatAdapter.get_feedback_checkpoint(session_id)` and binds the
  immutable typed `ChatFeedbackCheckpoint` for the same cookie session before recording a S10O gap.
  There is no setter/private-map access; client answer text, citations, structured payload, release
  IDs, or evidence IDs cannot establish gap lineage.
- The candidate app registers only health, S11A chat/reset/feedback, S10O gap list/detail, and S11B
  read-only admin routes. Missing/wrong V2 runtime returns a stable typed `503` without registering or
  falling back to a legacy route.
- FastAPI framework documentation is disabled with `openapi_url=None`, `docs_url=None`, and
  `redoc_url=None`. The exact known API allowlist is `GET /api/health`; S11A `POST /api/chat`,
  `/api/chat/feedback`, and `/api/chat/session/reset`; S10O gap list/detail; and the six S11B
  read-only admin routes. Outside `/api`, only `GET /`, `GET /browse`, `GET /chat`, and the `/static`
  mount are registered.
- The candidate removes the legacy global permissive `CORSMiddleware`; retained built-in pages are
  same-origin, and unknown `OPTIONS` requests with CORS preflight headers still reach the typed
  reject-only sink rather than returning success.

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

- One reject-only `/api/{path:path}` sink is registered after every known API route and before static
  routes for exactly `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, and `DELETE`. It returns the
  same typed `404` without resolving a runtime or producing an effect. It is an explicit non-writer
  allowlist entry; unknown legacy mutation paths cannot become `405`, HTML, or SPA success.
- Candidate `browse.html` exposes release status, Knowledge Gaps, and four read-only domains. It uses
  escaped rendering, imports no seed/pipeline/write/index consumer, and either uses the V2 read
  endpoints or shows bounded runtime unavailability. It does not
  call `/api/data/*` or legacy domain paths.
- Legacy React is `reference_only`, byte-preserved, unmounted, and unimported; no React/npm build is
  required for S11B.
- The non-blocking React byte-preservation receipt binds the Specified 22-file
  `apps/admin-console/frontend/src/**` sorted path-plus-raw-file-SHA-256 inventory digest
  `99abf5922399cd8bf20990934fa251c2a246da300fd4af3af384e6a9478ead77` before and after S11B.
- The one sanctioned offline writer accepts explicit request metadata/content and invokes
  `create_postgres_evidence_landing(...).ingest(...)` exactly once. It prints the exact typed
  `LandingReceipt` and performs no other data effect.
- Evidence ingestion requires explicit database URL, expected database, target kind, accepted
  backup-gate root, request JSON, S2B `source_id`, `namespace`, `member_relative_path`, and matching content
  SHA-256. Only exact `isolated-candidate` or `disposable` targets are allowed; there is no arbitrary
  content-file input.
- The CLI-local metadata shape contains every applicable `IngestEvidenceRequest` field except
  `content`; it rejects a caller-authored `content` key, requires non-null
  `expected_content_sha256`, and rejects unknown fields before opening content.
- The CLI calls `create_postgres_evidence_landing(...)` exactly once before path/content access, so
  that accepted factory resolves and verifies the explicit target, S2B gate, connection, and target
  identity. It retains the returned adapter; content-binds the accepted S2B backup manifest, restore
  verification, and acceptance record; selects exactly one member-manifest row by
  `(source_id, namespace, relative_path)`; requires exact request locator
  `s2b-restore://{accepted_run_id}/{namespace}/{relative_path}`; derives only
  `restore_root / namespace / relative_path`; and requires the corresponding restore source row to
  be passed, hash verified, and copy independent. It then requires current size to equal the member
  row and restore inode/device to differ from original, backup object, and member-manifest files;
  rejects symlink/non-regular/original/backup/object/alias-escape paths; reads that restore member
  exactly once; verifies current SHA-256 against both the S2B member hash and request hash; constructs the real
  request from those bytes, and calls the retained adapter's `ingest` exactly once. Arbitrary or
  newly collected/staged files are forbidden. The CLI does not duplicate target/connect logic.
- The one sanctioned retrieval diagnostic is a black-box HTTP smoke caller requiring an explicit
  base URL and expected release. It validates bounded V2 trace structure and does not judge prose,
  establish external truth, or load storage/provider state.
- A content-addressed versioned inventory classifies every retired registered router, frontend route,
  legacy writer/retrieval/index module, and executable legacy script as `reference_only`, `replaced`,
  or pending S11C disposition, with an exact V2 replacement where one exists.
- The executable-script discovery baseline is exactly 140 pre-S11B paths: 116 Python plus 24 shell.
  Its sorted path-list hash is
  `9235ceaf2bade6ae5012dc2db74d7ab5c994ba0151ea7cf40c602bfcdd0aa654`, and its sorted
  path-plus-raw-file-SHA-256 digest is
  `9512e595fc49d9b3b7d2cce789d72b2ea4e8421e1c4e8b5d34de7541bc3569d3`. Candidate discovery covers
  those paths plus exactly the three new sanctioned Python CLIs, for 143 post-S11B inputs: evidence ingest, candidate smoke,
  and deterministic baseline capture. Python uses AST import/call/body
  inspection; shell uses deterministic command/path/target/table/collection scanning; neither kind
  is executed during discovery.
- The path-list digest hashes a UTF-8 compact JSON array of sorted paths; the path/hash digest hashes
  a UTF-8 compact JSON array of sorted `{"path":...,"sha256":...}` objects with sorted keys.
  Neither digest input has a trailing LF. The React path/hash baseline uses the same no-LF encoding.
- Inventory bytes are canonical. A file identity is an exact-case repository-relative POSIX path;
  absolute paths, backslashes, empty/`.`/`..` segments, repeated separators, NULs, symlink aliases,
  and repository escapes are invalid. A module identity is dot-separated Python identifiers. Each
  entry has exactly one `path` or `module`, receives a `path:` or `module:` canonical prefix, is
  sorted within its category, and cannot duplicate any retired or sanctioned identity. The loader
  requires UTF-8 JSON reserialized with `ensure_ascii=False`, sorted keys, compact separators,
  `allow_nan=False`, and one trailing LF to equal the source bytes, then hashes those exact bytes.
  Discovery and S11C use the identical canonicalizer.
- The S11B receipt freezes the exact inventory SHA-256, category/disposition counts, and exact sorted
  `s11c_disposition` `(top-level category, path/module)` entries/count. The authoritative raw-byte
  hash is at exact JSON pointer `/legacy_consumer_inventory/sha256`; each entry is represented as
  `{"inventory_category": <top-level category>, "inventory_path": <path-or-module>}`. The immutable
  base count is never rewritten. S11C cannot close Tasks 11.1-11.5 until its separate overlay covers
  every frozen pair exactly once, leaves zero unresolved entries, and retired-test disposition is
  recorded.
- The receipt also records `broad_test_baseline.runs`: exact argv tokens/exit code, collected-nodeid
  artifact path/hash, JUnit artifact path/hash, and each failure/error's exact nodeid, outcome, and
  normalized signature hash. Normalization changes only CRLF, the exact run-mode `--basetemp` root
  to `<pytest-tmp>/` first, and the exact repository root to `<repo>/` second before hashing
  `outcome + LF + normalized_message + LF + normalized_body`. Message/body come from the persisted
  JUnit failure/error element so S11C can independently recompute the signature; the ephemeral
  report hook supplies nodeid/phase/outcome and lifecycle bijection only. Phase is stored separately and must
  remain in exact JUnit/report-hook bijection.
  `unrelated_preexisting` is unavailable in S11C without an exact retained baseline row.
- Only `capture_canonical_v2_s11b_baseline.py` produces that subtree and its content-addressed
  artifacts. Its fixed partitions use no `-k` or known-failure/node-ID filter. Admin uses exactly
  `-m "not requires_classifier_llm"` and records the sole deselected node
  `tests/test_classifier_benchmark.py::test_classifier_benchmark`; the explicit external marker is
  the only suite filter. Before collection the producer sets `PYTHON_DOTENV_DISABLED=1`, holds every
  sensitive database/index/provider environment name present-but-empty. Socket guard v2 permits
  AF_INET `connect` only to numeric `127.0.0.1:<exact port>` when the matching socket object in the
  same child called the patched `listen` after guard installation, remains live, and reports
  `SO_ACCEPTCONN=1`; this sole exception exists for the required black-box candidate smoke test.
  AF_INET6, unowned/closed/wrong-port/non-loopback AF_INET, every inet `connect_ex`, and every
  psycopg connect remain forbidden. AF_UNIX remains allowed only below an exact producer-owned
  temporary root. That root is a fresh `0700` `/tmp/s11b-*` directory, not ambient `/tmp`, and keeps
  the encoded `guard-probe.sock` path within the Linux 107-byte AF_UNIX limit.
  Before child startup it binds `TMPDIR`, `TMP`, `TEMP`, the exact child-stage paths, and the
  intended pytest temp root beneath that owned root. The early plugin installs guards in
  `pytest_load_initial_conftests`; its `tryfirst` `pytest_configure` then replaces
  `config.option.basetemp` with `CANONICAL_V2_S11B_PYTEST_TEMP` and, for run mode only,
  `config.option.xmlpath` with `CANONICAL_V2_S11B_JUNIT_STAGE` before collection, fixture, or JUnit
  write effects. Thus Milvus Lite sockets cannot use ambient `/tmp`. The receipt content-binds
  producer hash, environment names, guard versions, allowed roots, marker/deselection/collection
  evidence, preflight self-probes, and every blocked-test row. Before child startup it removes any
  inherited `PYTEST_CURRENT_TEST`; at session finish it restores every sensitive name to
  present-empty before writing the session-finish receipt update, including proxy names intentionally deleted
  by legacy tests. Child schema
  `canonical-v2-s11b-child-guard-v3` and baseline signature
  `canonical-v2-s11b-baseline-signature-v3` add
  `attempt_attribution=pytest-current-test-report-v1`. One process-local `threading.RLock`
  serializes every guard-state mutation with its receipt snapshot/write, retaining all concurrent
  duplicate attempts as valid JSON. The dedicated child does not restore the patched
  socket/psycopg/dotenv guards during `pytest_unconfigure`; the patches and live guard state remain
  installed through process exit, including late workers and `atexit` callbacks. Any unattributed
  late attempt is physically blocked, recorded in `forbidden_attempts`, and causes parent rejection.
  Only the bytes read by the parent after the subprocess has fully exited are the terminal child
  receipt.
  A non-probe socket/psycopg attempt is stored
  only in `blocked_test_attempts` when the guard blocks it before effect in run mode while pytest's
  exact active `<nodeid> (call)` context is visible, including worker threads spawned during that
  call. The parent requires collected membership, exactly
  one matching report row, a valid report outcome, and child exitstatus equal to subprocess
  returncode; top-level rows add `run_id`/`report_outcome` and retain duplicate attempts plus an
  exact count. `forbidden_attempts` remains exactly empty. Collection-time, setup/teardown,
  post-call worker, unattributed, unsupported, or unreported attempts fail closed; collection also
  permits no blocked-test or owned-loopback rows. Allowed owned-loopback connects remain separately
  content-bound child-receipt evidence. Guard/preflight failure, collection drift, interruption, or
  missing output emits no baseline run; the prior
  dotenv-restored real-DSN aborted run is ineligible.
- The producer wraps the original `dotenv.load_dotenv`, compares all sensitive environment values
  before/after, and in `finally` restores every member to its exact pre-call present-empty state
  before recording or raising on a mutation; preflight proves a no-op. The mutation RED asserts all
  49 values are still exactly `""` after the expected exception. `canonical-v2-no-external` has cwd
  `apps/miroflow-agent` and argv
  `["uv","run","pytest","-o","addopts=","-p","no:cacheprovider","-q","--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/tmp/canonical-v2-no-external/pytest","--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/canonical-v2-no-external.xml","tests/canonical_v2"]`.
  `admin-no-external` has cwd `apps/admin-console` and argv
  `["uv","run","pytest","-o","addopts=","-p","no:cacheprovider","-q","-m","not requires_classifier_llm","--basetemp=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/tmp/admin-no-external/pytest","--junitxml=../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/baseline/junit/admin-no-external.xml","tests"]`.
  The literal `--basetemp` and `--junitxml` values in these frozen argv arrays are audit sentinel
  tokens, not child write destinations. The early plugin performs the exact option rebinding above;
  collect mode also disables JUnit output. A child that does not perform that rebinding cannot
  produce a valid guard receipt.
  Collection removes the JUnit token and inserts `--collect-only` immediately before the test path.
  Nodeid artifacts are UTF-8, lexicographically sorted unique, one LF-terminated nodeid per line, no
  summary. Every collected nodeid maps through pytest's exact JUnit address mangling to one unique
  `(classname,name)` testcase and every testcase maps back; positional matching is forbidden. Each
  executed nodeid has one setup and teardown report plus exactly one call report iff setup passed,
  with no duplicate phase, and its derived terminal `passed|skipped|failure|error` outcome equals
  the JUnit child outcome. Every failure/error annotation belongs to its parent testcase and matches
  one exact identity/lifecycle report row. Missing, duplicate, ambiguous, partial, or mismatched
  JUnit/report-hook/nodeid evidence fails closed.
  Collection must exit exactly `0`; a run may exit only `0|1`. Pytest codes `2|3|4|5` and signal
  exits are rejected even when child receipt and subprocess agree.
- Each run uses a fresh exclusive child stage beneath `/tmp/s11b-*` plus a separate parent-only
  stage on the output filesystem, and rejects any pre-existing stage, final nodeid, JUnit, or
  baseline-row target. The child writes only beneath the owned `/tmp` stage/temp tree, completes parsing and exact
  JUnit/report-hook/nodeid bijection, then copies validated child artifacts into a parent-only stage
  on the output filesystem and rechecks their SHA-256 before same-filesystem hard-link promotion.
  It promotes new artifacts without overwriting existing bytes.
  Only after every promotion succeeds may it expose the baseline row. In `finally`, on success,
  failure, or interruption, it terminates only owned child processes and removes the unpromoted
  stage plus the owned
  `TMPDIR`/`TMP`/`TEMP`/`--basetemp` tree. Any failure removes all newly promoted artifacts and emits
  no baseline row; pre-existing outputs remain untouched. A valid receipt requires `cleanup=true`.

The sole sensitive-environment authority is this literal sorted 49-name tuple; discovery, unions,
and host-dependent additions are forbidden:

```python
SENSITIVE_ENV_NAMES = (
    "ALL_PROXY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "API_KEY",
    "BOCHA_API_KEY",
    "CANONICAL_V2_BACKUP_GATE_ROOT",
    "CANONICAL_V2_DATABASE_URL",
    "CANONICAL_V2_EXPECTED_DATABASE",
    "CANONICAL_V2_TARGET_KIND",
    "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    "CANONICAL_V2_TEST_DATABASE_URL",
    "CANONICAL_V2_TEST_EXPECTED_DATABASE",
    "CANONICAL_V2_TEST_TARGET_KIND",
    "CHAT_MILVUS_URI",
    "DASHSCOPE_API_KEY",
    "DATABASE_URL",
    "DATABASE_URL_TEST",
    "E2B_API_KEY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "JINA_API_KEY",
    "JINA_BASE_URL",
    "LOCAL_LLM_API_KEY",
    "LOCAL_LLM_BASE_URL",
    "MILVUS_URI",
    "NO_PROXY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENALEX_API_KEY",
    "OPENALEX_KEY",
    "REASONING_API_KEY",
    "REASONING_BASE_URL",
    "S2_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "SERPER_API_KEY",
    "SERPER_BASE_URL",
    "SGLANG_API_KEY",
    "SUMMARY_LLM_API_KEY",
    "SUMMARY_LLM_BASE_URL",
    "TENCENTCLOUD_SECRET_ID",
    "TENCENTCLOUD_SECRET_KEY",
    "VISION_API_KEY",
    "VISION_BASE_URL",
    "WHISPER_API_KEY",
    "WHISPER_BASE_URL",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
```

The receipt's `present_empty_sensitive_env_names` array equals `list(SENSITIVE_ENV_NAMES)` exactly,
including order and count. All four `CANONICAL_V2_TEST_*` gates remain present-empty in B6;
separate explicit disposable-database acceptance is outside this producer.

The exact receipt handoff shape is below. The shown numeric loopback port illustrates the required
integer type; an emitted row contains the exact ephemeral port observed in that child.

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
  },
  "broad_test_baseline": {
    "signature_schema_version": "canonical-v2-s11b-baseline-signature-v3",
    "producer_path": "apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py",
    "producer_sha256": "<raw-byte SHA-256>",
    "guard_preflight": {
      "python_dotenv_disabled": "1",
      "present_empty_sensitive_env_names": [
        "ALL_PROXY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "API_KEY",
        "BOCHA_API_KEY",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
        "CANONICAL_V2_DATABASE_URL",
        "CANONICAL_V2_EXPECTED_DATABASE",
        "CANONICAL_V2_TARGET_KIND",
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
        "CHAT_MILVUS_URI",
        "DASHSCOPE_API_KEY",
        "DATABASE_URL",
        "DATABASE_URL_TEST",
        "E2B_API_KEY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "JINA_API_KEY",
        "JINA_BASE_URL",
        "LOCAL_LLM_API_KEY",
        "LOCAL_LLM_BASE_URL",
        "MILVUS_URI",
        "NO_PROXY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENALEX_API_KEY",
        "OPENALEX_KEY",
        "REASONING_API_KEY",
        "REASONING_BASE_URL",
        "S2_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
        "SERPER_API_KEY",
        "SERPER_BASE_URL",
        "SGLANG_API_KEY",
        "SUMMARY_LLM_API_KEY",
        "SUMMARY_LLM_BASE_URL",
        "TENCENTCLOUD_SECRET_ID",
        "TENCENTCLOUD_SECRET_KEY",
        "VISION_API_KEY",
        "VISION_BASE_URL",
        "WHISPER_API_KEY",
        "WHISPER_BASE_URL",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy"
      ],
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

The disposition array is sorted by `(inventory_category, inventory_path)` and its count equals its
length. The shown zero is only the valid empty example; a non-empty immutable base is resolved by
S11C's separate overlay, never rewritten.
- Static `/domains/{domain}/export` is registered before dynamic
  `/domains/{domain}/{canonical_id}`. Unknown `/api/{path:path}` returns explicit `404` before any
  static/catch-all route and never receives HTML/SPA success.
- Static/runtime guards discover executable scripts and fail on any unclassified legacy dependency.
  They prove the candidate app and sanctioned CLIs import no quarantined module.
- Quarantined sources are not registered routes, candidate imports, subprocess targets, operator
  commands, or fallbacks. They may remain source-only historical comparison evidence until S11C.
- All query/admin/feedback execution remains read-only with respect to active canonical knowledge,
  source identities, release pointers, indexes, original sources, and forensic artifacts.

## Non-goals

- No complete S12 candidate build, new source acquisition execution, real-provider acceptance,
  claim-level corpus execution, latency/cost gate, or final user acceptance.
- No Task `11.1`-`11.5` checkbox, aggregate repository consumer acceptance, retired-test closure, or
  claim that every historical test/script remains supported.
- No generic admin workflow, arbitrary assertion/decision editor, direct canonical correction,
  batch gap remediation, scheduler, queue, SLA, auth redesign, or durable UI session store.
- No rewrite of every legacy domain collector/parser. Collectors may emit immutable artifacts; only
  the V2 landing interface is sanctioned as a database writer.
- No second `KnowledgeBuild`, index builder, release publication framework, query runtime, provider
  registry, or compatibility layer for V042 IDs/columns/collection names/global readiness.
- No broad deletion or movement of V001-V042 migrations, old route/page files, writer modules, or
  scripts. S11C owns delete-versus-reference disposition after aggregate checks.
- No preservation promise for legacy admin endpoint paths, pipeline stages, seed registry, quality
  mutation, prose-gold evaluation, direct SQL order, or old dashboard counts.
- No generic `DATABASE_URL`/`DATABASE_URL_TEST`/`MILVUS_URI`/`CHAT_MILVUS_URI` fallback, active/latest
  release discovery, original-source access, promotion, Cutover, Commit, Push, PR, Archive, or
  destructive cleanup.

## Allowed scope

- Create `apps/admin-console/backend/services/canonical_v2_admin.py` for the one private runtime.
- Create `apps/admin-console/backend/api/canonical_v2_consumers.py` for bounded read-only V2 admin
  routes.
- Modify `apps/admin-console/backend/canonical_v2_deps.py` and `backend/main.py` only to
  resolve/register explicit Accepted S10O/S11A/S11B candidate runtimes through V2-only imports and
  remove accepted-path legacy imports/routes/seed cron; preserve the Accepted zero-arg S10O getter/
  composer and add/install only the request getter override.
- Modify `apps/admin-console/backend/api/canonical_v2_chat.py` only for server-bound S10O feedback;
  Accepted S11A chat/reset behavior remains unchanged.
- Modify `apps/admin-console/backend/static/browse.html` only to consume V2 reads or show bounded
  unavailability.
- Keep `apps/admin-console/frontend/**` byte-identical and inventory-classified `reference_only`;
  the candidate app does not mount or import it.
- Add one focused admin migration owner in
  `apps/admin-console/tests/test_canonical_v2_consumer_migration.py`.
- Add `apps/miroflow-agent/scripts/run_canonical_v2_evidence_ingest.py` and its focused owner.
- Add `apps/admin-console/scripts/smoke_canonical_v2_candidate.py` and its focused owner.
- Add `apps/miroflow-agent/scripts/capture_canonical_v2_s11b_baseline.py` and its focused producer
  owner; it is the sole broad-baseline artifact producer.
- Add the versioned legacy consumer inventory, loader/validator, and boundary owner under Canonical
  V2.
- Add S11B-local `baseline/collected/*.txt` and `baseline/junit/*.xml` only as content-addressed broad
  baseline evidence referenced by the Candidate receipt.
- Update this contract, S11B audit/plan, add an S11B receipt after Candidate evidence, and update
  existing status/evidence pointers after acceptance.

## Forbidden changes

- Any algorithm/contract edit to Accepted Canonical V2 planning, read, answer, session, gap,
  projection, relationship, landing, build, index, or release-publication modules to make consumer
  wiring easier.
- Any schema/migration edit, V001-V042 rewrite, original/forensic source access, index byte mutation,
  release pointer/alias change, provider mutation, or production-like target.
- Any registered candidate route importing `get_pg_conn`, `get_retrieval_service`, direct SQL, a
  domain canonical writer, legacy `SessionContext`, seed/pipeline subprocess launcher, Milvus client,
  old collection-name helper, or global readiness/quality gate.
- Any candidate import of `backend.api.chat`, `backend.deps`, or legacy React; any V2-only module
  importing those legacy modules.
- Candidate use of the environment/`lru_cache` gap factory, direct pre-S11B chat state, loose
  manifest/projection/relationship inputs, cross-wired app-state members, or a plan path that omits
  the runtime-owned SupplementalBudget/eligible EnumerationPolicy controls.
- Replacing, changing the signature of, or removing `get_knowledge_gap_operations` or
  `_compose_operations`; using the environment composer from a candidate request; or installing an
  override other than the exact old-getter to new-request-getter identity.
- Any online PATCH/DELETE/batch quality/direct enrichment/direct upload-to-canonical/build/promote/
  Milvus-backfill endpoint.
- Trusting client answer/citation/structured JSON, URL equality, query wording, old V042 IDs, or an
  undisplayed candidate as feedback, identity, traversal, or evidence authority.
- Mutable/caller-authored feedback checkpoints, checkpoint setters/private-map access, content read
  before target/gate/path checks, multiple content reads, or admitting symlink/non-regular/protected
  original paths.
- Arbitrary content-file or non-member staging ingest, a member absent from the accepted S2B
  manifest/restore/acceptance graph, non-canonical inventory bytes/aliases, or a hand-authored,
  unsafe, aborted, guardless, `-k`-filtered, or known-failure-filtered broad baseline.
- A feature flag or exception fallback that re-registers/calls the legacy route, fixed handler,
  retrieval service, V042 writer, or direct index mutation when V2 is unavailable.
- A new public framework, generic repository/graph browser, dynamic SQL/filter language, workflow
  engine, scheduler, global service locator, or implicit latest-release resolver.
- Moving/deleting broad legacy trees, weakening historical tests, hiding failures with skip/xfail/
  importorskip, treating prose/reference answers as a pass/fail oracle, or using live credentials/
  network in deterministic owners.
- Checking any OpenSpec task, changing acceptance thresholds/behavior artifacts, claiming aggregate
  S11 acceptance, or changing the ledger count for S11B.
- Commit, Push, PR, Archive, promotion, Cutover, source writes, or destructive cleanup.

## Expected unchanged behavior

- Accepted S1-S10O and S11A deep-module, release, query, answer, session, gap, and verification
  contracts remain exact. S11B consumes them and does not reinterpret them.
- The S11A chat request/response envelope, cookie semantics, release continuity, exact option binding,
  evidence grounding, conditional continuation, and deterministic degradation remain unchanged.
- S10O gap storage, closure requirements, immutable history, admin list/detail fields, and no-online-
  canonical-write invariant remain unchanged.
- Four public domains, internal Person/Technology auxiliary boundaries, Product capability
  non-propagation, path eligibility, and source lineage remain exact.
- Legacy source files and historical direct-call tests remain present until S11C disposition, though
  they are absent from the candidate app and sanctioned entrypoint graph.
- Original PostgreSQL/Milvus/forensic sources, candidate/index bytes, active pointers, provider
  state, remote Git state, and task ledger remain unchanged.

## TDD RED contract

Add two exact-target owners:

```python
def test_s11b_candidate_app_exposes_only_release_bound_v2_consumers(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ...

def test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

Before acquiring a release/database fixture, constructing `TestClient`, importing a retired module,
or reading source content, their seam checks require the S11B runtime/router and inventory/loader.
The candidate seam list also requires `compose_canonical_v2_consumer_runtime` and
both candidate request getters, plus the route-shell/candidate factories, while asserting both
Accepted predecessor getters remain exact and the FastAPI override key/value identities are exact.
The Admin owner top level imports only standard library, pytest, and the `TestClient` type, uses only
built-in `request`/`tmp_path`/`monkeypatch`, and dynamically resolves every seam before importing
`backend.main` or constructing a client. Its focused commands use `--noconftest`; broad baseline does
not. The exact Admin commands are:

```bash
cd apps/admin-console
uv run pytest -o addopts='' -p no:cacheprovider --noconftest -q tests/test_canonical_v2_consumer_migration.py -k s11b_candidate_app_exposes_only_release_bound_v2_consumers
uv run pytest -o addopts='' -p no:cacheprovider --noconftest -q tests/test_canonical_v2_consumer_migration.py -k s11b_candidate_app_exposes_only_release_bound_v2_consumers --runxfail
uv run pytest -o addopts='' -p no:cacheprovider --noconftest -W error -q tests/test_canonical_v2_consumer_migration.py::test_s11b_candidate_app_exposes_only_release_bound_v2_consumers
```

Normal RED is exactly one strict xfail per owner. Forced RED is exactly one named
`_MissingS11BAdminRuntime` or `_MissingS11BLegacyInventory` failure before any effect. No production
or non-RED test edit may precede the observed RED.

GREEN uses actual Accepted S11A/S10O interfaces and an exact accepted `PublishedRelease`,
`ReleaseVerification`, `IsolatedReleaseBundle`, and matching `IndexProjectionRequest` through the
production aggregate composition. Test-local loose projection/relationship inputs, fake planner/
read/answer/gap algorithms, test-only plan-control wrappers, legacy SQL, or monkeypatched V042 rows
cannot prove the vertical.
The boundary owner remains strict-xfailed until inventory/loader and all three sanctioned CLIs plus
their focused owners exist; inventory alone cannot make it GREEN.

## Observable demo contract

One explicit fixture candidate application demonstrates:

```text
GET status
  -> one release, manifest, four typed projection populations, typed gap summary

GET domain list/detail/related
  -> same release, typed fields, evidence/field lineage, limitations,
     and accepted relationship/read trace

POST /api/chat
  -> Accepted S11A release/plan/lanes/evidence/claims trace

POST /api/chat/feedback with same cookie
  -> typed S10O gap bound to the server-retained S11A trace, not client JSON

GET V2 gap detail
  -> same release and exact feedback lineage

run_canonical_v2_evidence_ingest.py against disposable candidate
  -> exact LandingReceipt, no active release/index/canonical mutation

smoke_canonical_v2_candidate.py against test server
  -> expected same release and bounded V2 trace
```

The demo proves chat/admin/gap dependencies are the exact members of one aggregate app-state
runtime. Every observed plan carries the production-composed SupplementalBudget; the eligible typed
displayed Company→Patent relationship additionally carries the representative EnumerationPolicy, while an
ineligible request does not.

All retired routers, fixed handlers, SQL/retrieval factories, canonical writers, direct Milvus
builders, and subprocess launchers raise if invoked. A passing demo therefore proves the V2 consumer
graph rather than a compatibility mapper around legacy behavior.

## Required checks

- S10O and S11A contracts and final receipts are Accepted before RED or implementation edits.
- Each focused normal RED is exactly `1 xfailed`, with zero fail/error/XPASS.
- Each focused forced RED is exactly one named missing-seam failure before effects.
- Focused backend/boundary/CLI GREEN owners pass with warnings as errors and no skip/xfail/XPASS.
- Candidate route enumeration equals the frozen known API allowlist plus the exact seven-method
  reject-only sink and the exact four-entry static allowlist. Framework docs/OpenAPI and the React
  SPA are absent; no legacy data/admin/pipeline/seed/upload/batch/review router or writer endpoint
  remains registered.
- Candidate import graph contains no direct SQL connection, legacy canonical writer, fixed handler,
  `RetrievalService`, global readiness, old collection-name, Milvus client/backfill, seed cron, or
  subprocess launcher.
- Candidate import graph contains neither `backend.api.chat` nor `backend.deps` nor legacy React;
  S11A/S10O/S11B are imported only through V2-only modules.
- Admin status/list/detail/facet/export/related and chat-feedback-gap results bind one exact release
  and reject cross-release/forged/unbounded inputs before downstream effects.
- Runtime owners prove loose projection/relationship inputs are impossible, the accepted
  verification/bundle/index request exact-round-trip and cross-bind, all candidate getters resolve
  one aggregate app-state identity, every plan has the runtime SupplementalBudget, and only eligible
  typed displayed relationship plans receive the representative EnumerationPolicy.
- Four-artifact graph owners reject wrong/subclass/hostile same-class values, forged manifest hash,
  rejected or identity-drifted verification, candidate/index replay drift, missing/cross-wired/
  drifted relationship authority, and fifth domain with zero opaque-port effects.
- Per-call owners compare the full aggregate-derived `PlanningReleaseBinding` before read, validate
  available typed EvidenceSet continuity/closure/receipts before answer/response, validate answer
  closure before commit, and validate checkpoint presence/release before gap record, with exact
  effect counters.
- Dependency owners preserve the zero-arg S10O getter/composer, freeze the one-Request new getter,
  exact override identity, stable missing/wrong aggregate `503`, exact member identity, candidate
  success while the environment composer raises, and the unchanged direct S10O owner.
- Chat/app owners preserve the Accepted direct-state chat getter and override it only in a fresh
  factory-created candidate with the aggregate-only candidate getter. Module route shell has no
  aggregate/overrides; direct chat state cannot rescue a missing/wrong candidate aggregate; S11B
  owner/smoke/import graph use the factory.
- Admin focused normal/forced/GREEN commands use exact `--noconftest` argv and pass the dynamic seam
  sentinel before `backend.main` import/TestClient; its top-level imports and fixtures remain the
  frozen minimal set. Broad baseline retains normal conftest.
- Admin negative matrices exhaust the exact per-domain filter/facet/sort/relation allowlists and all
  pagination/facet/export/query/value bounds, including partial pairs and unsupported directions.
- Focused backend/static tests prove `browse.html` safely renders only sanctioned V2 reads and no
  legacy mutation/index/pipeline/seed control or endpoint string; React remains byte-identical and
  unmounted, with no npm/Vitest/Vite acceptance gate.
- Evidence-ingest CLI rejects missing/ambiguous/generic/original targets, any arbitrary/non-member
  content path, S2B manifest/restore/acceptance drift, and hash mismatch; it succeeds only for an
  exact passed S2B restore member on an explicit accepted disposable/candidate target and changes
  only landing rows.
- CLI owners prove CLI-local metadata rejects `content`, requires `expected_content_sha256`, and
  fails unknown fields before effects; the accepted landing factory is called exactly once before
  path/content access and retained; target/gate/path rejection precedes any content open;
  symlink/non-regular/protected-original paths fail; and admitted bytes are read/hashed/ingested
  exactly once.
- Smoke CLI requires explicit base/expected release and validates the V2 trace without loading
  storage/provider state or prose gold.
- Every path in the frozen 116-Python/24-shell baseline plus the three sanctioned Python CLIs is
  inspected by the appropriate non-executing scanner; every discovered executable legacy
  script/module is classified; every sanctioned entrypoint is unclassified as legacy and imports no
  quarantined dependency.
- The boundary owner stays strict-xfailed until inventory/loader and all three CLI implementations/
  owners are complete, then its exact GREEN nodeid passes; no partial DAG removes xfail.
- The receipt freezes exact inventory path/hash/category/disposition counts and sorted
  category-plus-path `s11c_disposition` entries/count at
  `/legacy_consumer_inventory/sha256`, plus exact broad baseline argv/nodeid/signature evidence;
  export precedes dynamic detail; all seven unknown `/api/*` methods return typed `404`.
- Inventory tests reject every non-canonical path/module spelling, order, duplicate, alias, or JSON
  byte representation. Baseline-producer tests prove fixed complete partitions, no `-k`, the exact
  Admin external-marker exclusion and sole deselected node, exact 49-name tuple/list equality,
  dotenv mutation restoration-before-error with all 49 still empty, a real owned-loopback HTTP body
  plus its exact allowed-connect row, blocked unowned AF_INET and inet `connect_ex` probes, socket
  guard persistence through `pytest_unconfigure`, concurrent `atexit` duplicate retention and late
  forbidden-attempt rejection, exact v3 child-receipt and JUnit-recomputable v3 baseline-signature validation,
  fail-closed psycopg, unchanged owned AF_UNIX roots, fresh exclusive staging, stale-output rejection, complete
  parse/bijection before no-overwrite promotion, owned-child/temp cleanup on every exit path,
  `cleanup=true`, zero new row/nodeid/JUnit output on failure, and content-bound guard/preflight
  evidence.
- Final Accepted S10O and S11A owner commands pass unchanged.
- Complete no-external candidate admin-console and Canonical V2 suites have zero unexpected
  failures; intentionally retired historical failures are recorded for S11C rather than weakened.
- Ruff check/format, `py_compile`, changed-scope Pyright, focused static-UI tests, strict OpenSpec,
  `git diff --check`, scope, secret, generated-cache, fresh locked-offline wheel/package-
  content, source parity, and frozen-source checks pass.
- One lean implementation/test-integrity review reports zero open Critical/Important. Minor/YAGNI
  findings are recorded and non-blocking.

## Evidence to update

- This Slice Contract and the S11B audit/implementation plan.
- New `.agents/runs/rebuild-canonical-v2-knowledge-platform/s11b/verification-receipt.json` after
  Candidate evidence exists.
- S11B-local `baseline/collected/*.txt` and `baseline/junit/*.xml` created atomically only by the
  deterministic guarded baseline producer and referenced by hash from that receipt.
- Existing `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- After acceptance only: `.agents/portfolio.md`, current mainline/convergence status, and existing
  agent-link/change-log pointers needed to reference the S11B receipt.
- Do not change OpenSpec task checkboxes or acceptance claims for Tasks `11.1`-`11.5`.

## Stop conditions

- S10O or S11A is not Accepted, its receipt is missing/stale, or an Accepted predecessor regresses.
- Correct consumer wiring requires changing an Accepted Canonical V2 behavior contract/algorithm,
  schema, migration, provider framework, release/index manifest, source, or active pointer.
- The candidate cannot be composed from an exact accepted verification/bundle/index request, cannot
  install one aggregate chat/admin/gap runtime, or cannot bind SupplementalBudget and eligible
  EnumerationPolicy controls outside test code.
- The only way to serve candidate gaps would be changing the Accepted zero-arg S10O dependency or
  calling its environment composer rather than installing the exact FastAPI dependency override.
- Admin reads cannot be produced from accepted typed projection/relation/read interfaces without
  direct V042 SQL or fabricated compatibility fields.
- Chat feedback cannot bind a server-retained S11A receipt and would need to trust client-authored
  lineage or mutate canonical/index state online.
- Evidence ingestion requires a generic/original/production-like target, missing backup gate, source
  mutation, direct canonical write, or an implicit environment fallback.
- The candidate app requires a legacy router, fixed handler, retrieval service, direct Milvus
  mutation, global readiness, old collection name, subprocess launcher, or fallback to return data.
- Quarantine discovery reveals a cross-module schema/API/behavior decision that cannot be classified
  as an existing V2 replacement or historical reference without broad redesign.
- Complete candidate building, claim-level quality execution, aggregate retired-test disposition,
  S11 task closure, S12 acceptance, promotion, Cutover, or unresolved Critical/Important findings
  enter scope.

## Done means

- S10O, historical S11A, and S9J are Accepted; reviewed current S11B hashes support the refreshed
  Candidate gate; exact RED and minimal
  GREEN are recorded.
- The candidate app's entire registered data/operations graph is release-bound S11A/S10O/S11B with
  no legacy SQL/writer/retrieval/fixed-handler/global-readiness/direct-index path or fallback.
- Dashboard, four domain reads, typed relationships, V2 gaps, chat, and server-bound feedback form
  one observable same-release admin/product vertical.
- The minimal built-in `browse.html` consumer exposes only those supported surfaces and remains
  read-only for canonical/index state; legacy React is `reference_only` and unmounted.
- One explicit-target EvidenceLanding CLI replaces sanctioned domain database writers, and one
  black-box V2 smoke caller replaces sanctioned direct retrieval diagnostics; ingest reads only an
  exact accepted S2B restore member.
- The versioned inventory and guards exhaustively classify/quarantine retired entrypoints without a
  broad source deletion.
- The inventory receipt freezes its exact pointer/category-plus-path handoff and exact broad-baseline
  signatures plus guarded producer/preflight evidence for S11C; static export ordering, the exact
  framework/static/route policy,
  seven-method unknown-API `404`, typed feedback checkpoint binding, and retained-factory-before-
  single-read ingestion all pass their owners.
- Required checks and one lean review pass with zero open Critical/Important findings.
- S11B is Accepted as an S11C dependency checkpoint, but Tasks `11.1`-`11.5` remain unchecked and
  the live ledger has no S11B delta.

## Rollback note

Remove the S11B admin router/service, restore the prior S11A/S10O app registration, restore prior
`browse.html`, remove the evidence-ingest/smoke/baseline-capture CLIs and quarantine inventory/owners,
and restore the prior S11A feedback route. Re-registering legacy routes is permitted only for the
pre-S11B development comparison checkpoint; it does not make them accepted. No database, index,
source, provider, release pointer, task checkbox, Commit, Push, PR, Archive, promotion, or Cutover
state requires rollback.
