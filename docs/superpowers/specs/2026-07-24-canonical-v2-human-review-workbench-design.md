# Canonical V2 Human Review Workbench Design

Date: 2026-07-24
Status: User-approved on 2026-07-24; implementation in progress
Parent change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
Primary task: OpenSpec Task 2.8
Downstream gates: Tasks 8.1, 8.8, and 9.8

## 1. Context

The Accepted S2C review packet is deterministic and content-addressed, but it is not usable by a
human without opening JSON and constructing review/calibration records manually. The exact packet is:

- path: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/human-review-packet-v1.json`
- raw SHA-256: `222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e`
- content SHA-256: `d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb`
- 29 pending contract-review candidates
- 23 evidence-gap exclusion candidates
- 18 calibration families
- 160 unique hard requirements across the 29 pending candidates

The 160 hard requirements are not a 160-row LLM calibration pool. The packet contains one required
claim, three forbidden claims, 143 deterministic stage expectations, and a small number of entity,
variant, and policy requirements. The current evaluator invokes its semantic judge only for the one
required claim. A separate frozen observation bank is therefore a prerequisite for 60 meaningful
judge comparisons; the workbench must not manufacture that bank from requirement IDs alone.

The former Ready S2C3C2 slice required two humans and at least 50 double-reviewed samples per
relevant family. The owner has replaced that operational policy with one accountable human reviewer
and one deterministic, globally stratified set of 60 human labels. Evidence-bounded judging and
human calibration remain invariant; the active OpenSpec wording and v1 packet calibration templates
must be versioned to make the new global-stratification rule normative before implementation.

The workbench must be usable from the Candidate service itself. It must not require the reviewer to
run a separate React/Vite process, edit JSON, use a shell, or access Canonical storage.

## 2. Goals

1. Serve a focused three-pane review workbench at `/review` from the Candidate FastAPI process.
2. Let one named human review all 29 contract candidates and all 23 exclusion candidates.
3. Let that reviewer blindly label a deterministic set of 60 evidence-bounded judge samples.
4. Persist drafts and immutable submitted revisions in a dedicated SQLite database.
5. Resume the exact review after browser refresh or service restart.
6. Export canonical, content-addressed review evidence with an explicit non-accepting or
   acceptance-candidate status; only the latter requires all gates to pass.
7. Validate and apply the package to a new reviewed S2C artifact version without mutating the
   Accepted source packet or its predecessor artifacts.
8. Keep Task 2.8 open until attributable human input exists and the exported package passes the
   independent validator.

## 3. Non-goals

- No login, role, permission, or identity-provider implementation. Reviewer name/staff ID provides
  attribution, not authentication.
- No write to Canonical PostgreSQL, Milvus, the active release, the frozen S2C packet, or any Accepted
  predecessor artifact.
- No automatic OpenSpec checkbox, acceptance, commit, push, PR, archive, release, or Cutover.
- No implementation or execution of Tasks 8.1, 8.8, or 9.8 in this slice.
- No model-generated human label, reviewer impersonation, truth from model memory, or reference prose
  promoted to normative evidence.
- No separate frontend framework or new heavy dependency.
- No attempt to make multi-reviewer concurrency a product feature. Stale-tab protection remains
  required even with one accountable reviewer.

## 4. Source-of-truth and invariant decisions

### 4.1 Immutable inputs

The workbench reads the exact Accepted packet and the Accepted S2C artifacts it identifies. Startup
must verify the raw packet hash, packet content hash, source artifact identities, case accounting,
hard requirement IDs, and snapshot identities before returning any review task.

The workbench never rewrites the packet. A changed packet or source artifact makes the workspace
unavailable until a new workload is built and explicitly selected.

### 4.2 One human reviewer

One human supplies every contract, exclusion, and calibration decision in a review round. The
reviewer enters a non-empty display name and staff ID when opening the workspace. The canonical
reviewer ID is derived as `human:<normalized-staff-id>` and is bound to every submitted event. Staff
IDs are lower-cased ASCII matching `[a-z0-9._-]{2,64}`; display names are Unicode text and are never
used as an identity key.

This attribution is not authentication. A deployment binding to `0.0.0.0` must sit inside a trusted
network or behind an existing authenticated reverse proxy. The workbench must state this limitation
in its operating instructions.

### 4.3 Human workload

The initial human workload contains:

| Phase | Required final decisions | Purpose |
|---|---:|---|
| Contract review | 29 | Confirm that each structured contract accurately describes expected behavior |
| Exclusion review | 23 | Confirm whether the evidence-gap case may remain excluded |
| Blind calibration | 60 | Compare the evidence-bounded judge with human gold |
| **Total** | **112** | One accountable review round |

An `unable_to_determine` answer is recordable but never satisfies a final gate. It prevents an
acceptance-candidate export until the source contract/evidence is corrected or the reviewer submits a
superseding final decision. It may remain in a permanently non-accepting audit export.

### 4.4 Review-complete is not acceptance-ready

The UI and export validator distinguish:

- `review_in_progress`: required tasks have no final decision;
- `review_complete_blocked`: every task has a decision, but at least one decision or metric blocks
  acceptance;
- `acceptance_ready`: every required decision and calibration gate passes;
- `human_labels_sealed`: all 60 human labels are immutable and model results may be revealed;
- `calibration_failed_sealed`: sealed labels fail one or more calibration gates;
- `exported`: an acceptance-ready state has produced one content-addressed package.

Finishing the forms does not imply that Task 2.8 passes.

## 5. Reviewer experience

### 5.1 Page structure

The approved layout is a focused three-pane workbench:

- left: phase, progress, filters, and task queue;
- center: human-readable question, expected behavior, and frozen evidence/context;
- right: decision, rationale, autosave state, and submit/next action.

The header shows the reviewer identity, abbreviated packet hash, current phase, and total progress.
The page supports desktop keyboard navigation. Responsive behavior may stack the decision pane below
the content pane, but mobile optimization is secondary.

### 5.2 Phase 0: reviewer registration

The reviewer supplies display name and staff ID. Both are required. The server sets a random session
token in an `HttpOnly`, `SameSite=Strict` cookie and stores only its hash; JavaScript never receives
the token. Canonical identity remains server-side. Opening the same packet with the same staff ID
resumes the latest round that has not been locked by a successful acceptance-candidate export after a
new session token is issued.

### 5.3 Phase 1: contract review

The UI translates structured requirements into reviewable Chinese labels and descriptions while
retaining an expandable raw-structure view. The reviewer judges the expected contract, not a current
system answer.

Translations are deterministic mappings for known schema fields, not LLM summaries. An unknown
requirement kind is shown in its exact raw form and blocks approval until the renderer and review
policy explicitly support it. The mapping version/hash is bound to the workload and export.

Decisions:

- `approved`: the complete structured contract is correct and usable for acceptance;
- `needs_change`: one or more requirements are wrong, missing, or excessive;
- `unable_to_determine`: the supplied context is insufficient for a human decision.

`needs_change` and `unable_to_determine` require a rationale and block acceptance. Only `approved`
produces the exact eight-field human-review record expected by the S2C evaluator.

### 5.4 Phase 2: exclusion review

The UI shows the exact query, case identity, family, as-of, frozen contract, evidence-gap reason,
snapshot payload/source nature, and why the case is currently blocked. Historical reference prose is
clearly marked non-normative and is never shown as accepted evidence.

Decisions:

- `accept_exclusion`: the case may remain excluded because accepted claim evidence is unavailable;
- `require_evidence`: the case must not be excluded without new reviewed evidence;
- `unable_to_determine`: the reviewer cannot decide from the supplied context.

Every exclusion decision requires a rationale. Only `accept_exclusion` can satisfy the exclusion
gate. It does not fabricate evidence or make the excluded case acceptance-eligible.

### 5.5 Phase 3: blind calibration

Each calibration task displays one evidence-bounded judge request in human terms: candidate
observation, one hard claim requirement, exact as-of, and the supplied snapshots. The human labels
the request as `supported`, `unsupported`, or `unable_to_determine`.

The server must not include the model decision, agreement state, response hash, or any derivable
model-result field in a pre-submission response. Individual model decisions remain hidden throughout
the calibration phase; only after all 60 human labels are final may the summary reveal model
decisions and agreement. `unable_to_determine` blocks the round and does not count toward the 60 valid
pairs.

### 5.6 Phase 4: summary and export

The summary lists missing tasks, blocking decisions, stratum/family coverage, overall agreement,
critical false accepts, judge model/policy identity, and artifact hashes. A non-accepting audit export
is available at any review state so current attributable submitted feedback can be retained; it
records missing tasks and excludes mutable drafts. The acceptance-candidate export is enabled only in
`acceptance_ready` state. Both dialogs explain that export does not itself accept Task 2.8.

## 6. Calibration protocol

### 6.1 Deterministic workload

A deterministic two-stage builder produces `human-review-workload-v2.json` from the exact packet,
Accepted S2C artifacts, and checked-in fixture/badcase observations from the Canonical V2 query,
read, and answer paths. First it materializes a content-addressed candidate observation bank whose
rows satisfy a versioned evidence-bounded judge-request shape. Then it selects 60 distinct request
hashes from that bank. Human labels establish the gold result; fixture observations are stimuli, not
accepted truth.

Before the workbench slice becomes Ready, a dependency audit must prove that the frozen inputs contain
enough labelable requests for all quotas. If they do not, the Ready slice may add fixture-only
candidate observations with exact source locators and deterministic construction, but it may not
synthesize evidence, promote reference prose, use future S8/S9 acceptance results, or use the judge
model to author its own calibration stimuli.

The builder must:

- meet the fixed stratum quotas below;
- bind each task to case, contract, requirement, observation, snapshot, as-of, policy, and request
  hashes;
- use no model result when selecting tasks;
- allow multiple observations for one requirement only when their complete request hashes differ;
- fail rather than synthesize a task when the frozen observation bank cannot satisfy the quotas;
- emit deterministic canonical bytes and a content SHA-256.

| Stratum | Labels |
|---|---:|
| Claim/evidence support | 20 |
| Identity/entity | 10 |
| Context/relationship | 10 |
| Safety/Web | 10 |
| Insufficiency/assessment | 10 |

The workload includes explicit stratum rules and family membership so coverage is mechanically
auditable. The sample set is frozen before the judge runs and before the human sees any model result.
Original case-family counts remain reportable, but the five strata are the normative calibration
groups. The gate is the approved global threshold over this pre-stratified sample; the rejected 18
times 50 per-family protocol is not retained.

### 6.2 Judge identity and adapter

The judge is a true external dependency. The implementation defines one internal judge port and two
adapters:

- production adapter: invokes the explicitly configured evidence-bounded model and returns the
  existing recorded-judge decision schema;
- test adapter: deterministic fake with supported, unsupported, malformed, timeout, and
  cross-wired response modes.

The exact model ID and `evidence-bounded-judge-v1` policy ID are frozen into the workload and every
result. Credentials come only from existing approved environment variables and never enter SQLite,
HTTP responses, logs, or exports.

Before the model runs, the accountable owner/reviewer confirms a `judge-authorization-v1` record
containing authorizer ID, model ID, provider-profile ID, policy ID, workload hash, intended round ID,
timestamp, and content SHA-256. It contains no credential. Calibration cannot start without this
record.

All 60 model decisions are produced and frozen server-side only when the human labels are sealed.
The judge never receives human labels. A seal with any unresolved model response fails without
revealing model results and must be rerun under a new judge-run identity.

If the judge is unavailable, contract and exclusion review remain usable. Calibration is visibly
paused and cannot be exported.

### 6.3 Gates

One calibration round passes only when:

1. exactly 60 frozen tasks have valid human/model pairs;
2. all five fixed strata meet their quotas;
3. exact-match agreement is at least `0.80`;
4. at least 10 human labels are `supported` and at least 10 are `unsupported`;
5. at least five human-`unsupported` tasks are mechanically marked critical probes;
6. critical false accepts equal zero.

A critical false accept is a model `supported` decision paired with human `unsupported` for any:

- forbidden claim;
- material required claim with an evidence obligation;
- safety-guidance requirement;
- protected identity, slot, set, or constraint requirement.

A failed round ends as failed. The tool does not add labels to chase a passing score. A changed judge
model or policy requires a new round ID and independent export; the exact 60 sample selections remain
fixed so a retry cannot improve its score by resampling. If the policy changes the request bytes, a
new workload identity binds those bytes while preserving the same selected source observation IDs.
The failed round is never rewritten.

## 7. Deep module design

### 7.1 External seam

`ReviewWorkspace` is the deep module used by the FastAPI route module and by interface-level tests.
Its interface has three entry points:

```python
class ReviewWorkspace:
    def open(self, request: OpenWorkspace) -> WorkspaceView: ...
    def record(self, command: ReviewCommand) -> WorkspaceView: ...
    def export(self, command: ExportReview) -> ExportReceipt: ...
```

The interface includes these invariants and error modes:

- every request is bound to packet/workload identity and reviewer identity;
- `record` accepts draft or final-decision commands and returns the authoritative next view;
- final decisions use optimistic revision and idempotency keys;
- `export` is fail-closed and returns an immutable receipt;
- hash/configuration failures make `open` unavailable rather than returning partial work;
- stale revision is distinct from validation, storage, judge, and gate errors.

The module hides packet paths, workload construction, source-artifact reads, SQLite transactions,
revision resolution, calibration blindness, metric calculation, and export canonicalization. Deleting
the module would force those rules into every HTTP handler and test, so the module earns its seam.

### 7.2 Dependency classification

- Packet/source filesystem: local-substitutable; inject paths and test through temporary files. No
  external filesystem port is exposed.
- SQLite ledger: local-substitutable; test the real implementation against a temporary database. No
  repository interface is exposed merely for mocking.
- Clock and ID generation: in-process callables injected internally for deterministic tests.
- LLM judge: true external; use the internal judge port with production and fake adapters.
- Canonical PostgreSQL and Milvus: not dependencies of this module and must never be imported or
  connected by its implementation.

### 7.3 HTTP mapping

The HTTP route module remains thin and maps transport requests onto the three-entry interface:

- `GET /review` serves the static workbench;
- `POST /api/review/sessions` opens or resumes a reviewer round;
- `GET /api/review/workspace` calls `open` for the requested cursor/phase;
- `PUT /api/review/drafts/{task_id}` records a mutable draft;
- `POST /api/review/decisions` records an immutable final revision;
- `POST /api/review/exports` calls `export`;
- `GET /api/review/exports/{export_id}` downloads an existing verified export.

Pydantic request/response models reject unknown fields. Error payloads use stable codes and never
include filesystem paths, credentials, hidden judge values, or raw exception text.
Mutation routes require the strict session cookie plus a same-origin request check; no permissive
cross-origin mutation mode is added for this workbench.

### 7.4 Static frontend

The Candidate shell serves `review.html`, `review.css`, and `review.js` from its existing static
mount. The page uses semantic HTML and ordinary browser APIs. It does not add a framework or build
step. The browser is a renderer and command client; authoritative progress, decisions, blindness,
and export readiness remain server-side. Dynamic content is assigned as text, never interpreted as
HTML; the page ships a restrictive Content Security Policy.

## 8. Persistence model

The dedicated SQLite database lives under an explicitly configured review state directory. It uses
foreign keys, WAL mode, transactions, and schema versioning. The minimum logical records are:

- workspace metadata: packet, workload, source, model, policy, and schema identities;
- reviewer round: reviewer ID/display name, round ID, timestamps, and lifecycle state;
- draft: mutable, non-evidentiary data keyed by round and task;
- decision event: append-only payload, revision, rationale, superseded event, idempotency key,
  submitted time, and payload SHA-256;
- hidden judge result: request/response identity and decision, never returned before human submit;
- export record: canonical package identity, path, gate summary, and creation time.

Submitted events are never updated or deleted through the application. A changed decision appends a
new event whose `supersedes_event_id` names the previous final event. The current state is the highest
valid revision per task. Drafts may be overwritten and are excluded from every evidence hash.
Calibration labels may be revised only before `human_labels_sealed`; after model results are revealed,
later annotations cannot replace metric-eligible gold.

Unique constraints enforce one event per idempotency key and one revision number per round/task.
`record` performs revision check, insert, state recomputation, and response construction in one
transaction.

## 9. Export and S2C application

### 9.1 Export packages

`ReviewWorkspace.export` accepts one of two explicit modes:

- `review_evidence`: allowed at any review state, contains only submitted attributable state plus
  explicit missing-task accounting, and is permanently non-accepting;
- `acceptance_candidate`: allowed only when all decision and calibration gates pass.

Both canonical packages contain:

- packet, workload, source artifact, schema, judge model, and policy identities;
- reviewer identity and round identity;
- all submitted decision events and their revision chain hashes;
- the 29 final contract decisions and exact eligible eight-field review records;
- the 23 final exclusion decisions and accepted exclusion records;
- the 60 human labels and server-held judge decisions;
- family/stratum coverage, confusion matrix, agreement, and critical-false-accept count;
- gate status, creation time, file hashes, and package content SHA-256.

For an in-progress `review_evidence` package, the decision lists and missing-task accounting reflect
only submitted immutable events. Before `human_labels_sealed`, it contains judge authorization/run
identity and completion status but omits every judge decision, agreement field, response hash, and
derivable model-result signal. After sealing, model-result fields may be included. An
`acceptance_candidate` always contains the complete 29+23+60 accounting.

Only an `acceptance_candidate` package may enter S2C application. A `review_evidence` package exists
to preserve actionable human feedback and can never be reinterpreted as acceptance evidence.

Keys are sorted and JSON is canonicalized with the same project hashing convention. The exporter
writes to a temporary file, fsyncs it, atomically renames it, rereads it, and verifies both raw and
content hashes before recording success.

### 9.2 Validator and application

A separate run-local validator consumes only the export, frozen workload, frozen packet, and Accepted
S2C source artifacts. It reproduces every identity, count, revision, calibration, and gate check. It
does not trust the SQLite database or UI status.

When validation passes, the S2C application step may produce a new reviewed corpus/manifest version:

- 29 approved contracts become `human_reviewed` and bind exact human review hashes;
- 23 accepted exclusions remain non-eligible and bind exact human exclusion hashes;
- no excluded case gains fabricated claim evidence;
- the original Accepted packet and corpus remain byte-identical.

Task 2.8 can be proposed for acceptance only after the new artifacts, evaluator run, validator, and
independent review all pass. Tasks 8.1, 8.8, and 9.8 remain blocked until that acceptance.

## 10. Failure handling

| Failure | Required behavior |
|---|---|
| Packet/source/workload hash mismatch | Return workspace-unavailable; perform no review write |
| Missing or invalid reviewer identity | Return validation error; create no round |
| SQLite write/commit failure | Return failure; never report saved; safe retry with same idempotency key |
| Stale revision from another tab | Return `409 stale_revision` with current revision, without overwriting |
| Duplicate idempotency key, same payload | Return the original receipt |
| Duplicate idempotency key, different payload | Return `409 idempotency_conflict` |
| Judge unavailable/timeout/malformed output | Keep model result unresolved; pause calibration; never infer a label |
| Browser disconnect during autosave | Show unsaved state and prevent silent navigation loss |
| Incomplete review | Return gate checklist; permit only a non-accepting `review_evidence` export |
| Complete but blocking review | Permit only a non-accepting `review_evidence` export |
| Export write/reread/hash failure | Record no successful export and preserve prior verified exports |
| Unknown task, family, requirement, or snapshot | Reject before any mutation |

The UI may retry read operations. It must not automatically retry a final decision with a new
idempotency key because that could create an unintended new revision.

## 11. Configuration and operation

Configuration is explicit and fail-closed:

- packet path;
- Accepted S2C source root;
- review state directory;
- export directory;
- judge model ID and approved provider configuration.

No default may point to production PostgreSQL or Milvus. A convenience development command may set
the exact run-local paths, but the module validates their hashes rather than trusting the path.

The Candidate process may bind to `0.0.0.0`; deployment documentation must warn that reviewer
identity is attribution-only and require a trusted network or reverse proxy. Logs contain event IDs,
task IDs, stable error codes, and abbreviated hashes, but not prompts, evidence payloads, reviewer
rationales, model responses, or secrets.

## 12. Verification strategy

### 12.1 Workload and pure behavior

- deterministic 60-task selection from the frozen observation bank;
- exact five-stratum quotas and outcome/critical-probe coverage;
- no judge-result-dependent selection;
- packet/workload/source tamper rejection;
- decision state transitions, superseding revisions, and review-vs-acceptance state distinction;
- agreement, confusion matrix, critical false accept, and export gate calculations;
- canonical JSON and raw/content hash reproduction.

### 12.2 Interface-level integration

Tests use the real `ReviewWorkspace` with temporary source files and temporary SQLite, crossing the
same interface as production callers. They cover:

- register, resume, cursor/filter, draft, final submit, supersede, and export;
- duplicate idempotency, conflicting idempotency, and stale revision;
- restart recovery and deterministic current-state projection;
- judge supported/unsupported, timeout, malformed, cross-wired, and external-memory responses;
- incomplete, blocking, low-agreement, critical-false-accept, and passing rounds;
- non-accepting audit export versus acceptance-candidate export;
- absence of Canonical database/index connections or imports.

### 12.3 HTTP integration

FastAPI tests cover strict request/response shapes, stable errors, reviewer attribution, hidden model
fields, strict session-cookie/same-origin mutation behavior, download identity, and route availability
only on the Candidate shell. A network-level test asserts that no response before all 60 human labels
are final can reveal a judge decision through body, headers, task ordering, or status fields.

### 12.4 Browser verification

Browser automation covers:

- reviewer registration and resume;
- all three task types;
- keyboard navigation and visible focus;
- autosave, reload, stale-tab conflict, and blocked navigation;
- blind calibration before sealing and reveal only after all 60 labels are sealed;
- progress, blocked summary, successful summary, and export download;
- desktop and narrow viewport layout;
- no console errors or failed network requests on the happy path.

### 12.5 Exact artifact verification

The exact 52-case packet runs with a deterministic fake judge in automated E2E. The real judge is run
only in the attributable human round. Implementation may reach Candidate with fake-judge evidence,
but Task 2.8 remains open until the real exported package passes validation and independent review.

## 13. Planned file scope

Expected implementation areas are:

- `apps/admin-console/backend/main.py` for the explicit page/router installation;
- `apps/admin-console/backend/api/canonical_v2_review.py` for transport mapping;
- `apps/admin-console/backend/services/canonical_v2_review.py` for the deep module and internal judge
  seam;
- `apps/admin-console/backend/static/review.html`;
- `apps/admin-console/backend/static/review.css`;
- `apps/admin-console/backend/static/review.js`;
- focused backend, interface, HTTP, and browser tests;
- run-local deterministic workload builder, export validator, application tool, tests, slice
  contract, and verification evidence under the existing change/run.

If the deep module becomes too large, implementation-internal helpers may move into a private
`canonical_v2_review/` package. The external three-entry interface must not expand merely to expose
those helpers to tests.

## 14. OpenSpec and slice reconciliation

Before production code changes, the implementation plan must:

1. mark the former two-human/per-family-50 S2C3C2 Ready slice as rejected by explicit owner policy;
2. update the active claim-level acceptance spec and acceptance evidence to define the versioned
   single-human/five-stratum/60-label policy;
3. create a versioned calibration-policy artifact that mechanically supersedes only the v1 packet's
   empty calibration templates while leaving the packet bytes unchanged;
4. create one independently testable Ready slice under the existing OpenSpec Task 2.8 for the
   single-human workbench, workload, exporter, validator, and real-corpus application path;
5. preserve the OpenSpec invariant that scaled judging is evidence-bounded and human-calibrated;
6. version the new calibration/export schemas instead of silently reinterpreting the old v1 fields;
7. keep Task 2.8 unchecked through implementation Candidate;
8. require external human output before Task 2.8 acceptance.

No new OpenSpec change is required because the active change already owns Task 2.8 and its
claim-level human-calibration behavior. The detailed operational policy is versioned in the new slice,
schemas, and verification contract.

## 15. Rollback

Before human use, rollback is code removal plus removal of the unaccepted workload artifact. After
human use, code may still be disabled without deleting the dedicated SQLite database or exports;
those are attributable evidence and should be retained or archived. None of these actions requires a
Canonical database rollback because the workbench never writes Canonical storage.

## 16. Done conditions

### Implementation Candidate

- the Ready slice has been implemented without broadening scope;
- focused unit, interface, HTTP, browser, lint, type, OpenSpec, and diff checks pass;
- exact fake-judge E2E passes;
- independent code/design review has no open Critical or Important findings;
- Task 2.8 remains unchecked.

### Task 2.8 Candidate

- one attributable human has supplied all required final decisions and 60 valid calibration labels;
- the judge identity is authorized and recorded;
- agreement is at least `0.80` and critical false accepts equal zero;
- the canonical export, validator, new reviewed corpus/manifest, and exact evaluator run pass;
- independent review has no open Critical or Important findings.

### Task 2.8 Accepted

- the owner accepts the exact Task 2.8 Candidate evidence;
- only then is Task 2.8 checked and the reviewed oracle made available to Tasks 8.1, 8.8, and 9.8.
