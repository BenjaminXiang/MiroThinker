# chat-grounded-answer-contract Specification

## ADDED Requirements

### Requirement: Canonical atomic evidence

The chat service SHALL construct one ordered `evidence_items` list and SHALL use that same list for
prompt input, claim validation, API evidence, compatibility citations, and UI citation numbering.
Each evidence item MUST identify one atomic fact or coherent source span with a stable
`evidence_id`, canonical object identity, field and typed value, snippet, traceable source, source
lane, nullable record quality, relation tier, and limitations. Its provenance MUST extend the shared Evidence
contract: existing source-type enum, source URL or file, required fetch time, and optional confidence.
`record_quality` MUST be present and use the closed chat projection enum `record-quality-v1`:
`ready | needs_review | low_confidence | needs_enrichment | partial | rejected | null`. This MUST
NOT redefine the shared four canonical states: those four map directly; domain-local `partial` is
preserved for truthful partial-rich disclosure; `rejected` is permitted only in exclusion/audit
evidence and never as an eligible result; legacy `incomplete`/`shallow_summary` MUST normalize to
`needs_review` and are forbidden on the wire. JSON null is required for uncatalogued Web/relation-
only/no-retained-quality evidence. Null MUST NOT be interpreted as ready or replaced with an invented
quality/status value; a material absence uses a limitation.

#### Scenario: One evidence identity crosses every layer

- **WHEN** a retrieved paper title is supplied to synthesis and returned as a cited claim
- **THEN** the prompt, validated claim, API evidence item, derived legacy citation, and displayed
  citation SHALL all refer to the same `evidence_id` and paper ID
- **AND** its displayed number SHALL be the position of that evidence item in the canonical ordered
  list rather than an independently generated number

#### Scenario: Joined evidence is composed instead of discarded

- **WHEN** a professor-paper request retrieves both professor identity evidence and a page of paper
  evidence
- **THEN** the evidence builder SHALL include both domains in the canonical list
- **AND** building professor evidence SHALL NOT terminate before the joined paper evidence is added

#### Scenario: Live Web and secondary relationship metadata do not overload shared enums

- **WHEN** chat evidence comes from an uncatalogued live Web result or a secondary company-team
  relationship
- **THEN** the live Web result SHALL use shared `source_type=public_web` plus `source_lane=web`
- **AND** secondary status SHALL use `relation_tier=secondary` and a limitation rather than inventing
  a quality-status or shared source-type value
- **AND** Web/relation-only `record_quality` SHALL be null unless the evidenced canonical object has
  an actual stored quality enum
- **AND** every item SHALL retain a source URL/file and fetched-at timestamp

#### Scenario: Canonical local object originated from public Web

- **WHEN** a canonical local object was originally collected from a public Web source
- **THEN** its evidence MAY use `source_type=public_web` but SHALL keep `source_lane=local` and its
  canonical local object ID
- **AND** it SHALL remain eligible for the applicable local-ID gate

#### Scenario: Canonical fact has no retained shared source evidence

- **WHEN** a retrieved local fact cannot be joined to source type, URL/file, fetched-at, and
  supportable snippet required by the shared contract
- **THEN** the service SHALL NOT synthesize a URL from DOI/ID or use row timestamps/locators as
  provenance
- **AND** the fact SHALL be omitted or disclosed as unavailable in `partial_result`
- **AND** canonical cutover SHALL stop if a required P0 intent cannot be grounded without an
  out-of-scope schema/data/trust-boundary change

### Requirement: Stable evidence IDs are not display ordinals

The service MUST implement `evidence-id-v1` as `ev1_` plus lowercase SHA-256 over
`uint32_be(byte_length(json_bytes)) || json_bytes`, where `json_bytes` is UTF-8 RFC 8785 canonical
JSON of shared source identity/time, canonical object/field, discriminated typed value, and
normalized snippet. The canonical object MUST always include `source_url` and `source_file` as
string-or-null, normalize empty to null, require at least one non-null, and include both when both
exist. `evidence-url-v1` MUST accept absolute HTTP(S) without userinfo and use WHATWG parse/serialize
(lowercase scheme/host, WHATWG IDN/percent/dot-segment rules, no default port/fragment, serialized
query order/duplicates preserved). `evidence-file-v1` MUST use NFC logical POSIX paths, convert
backslash, collapse duplicate slash/`.` segments, preserve case, and reject `..`/NUL without
filesystem resolution. `fetched_at-v1` MUST parse offset-bearing RFC 3339, reject naive/leap-second
input, convert UTC, and serialize exactly six fractional digits plus `Z`. Other strings MUST use
Unicode NFC/LF; object keys/numbers MUST use RFC 8785. Response order MUST be absent. Unequal
canonical bytes with the same digest MUST fail as a collision; equal bytes deduplicate.

#### Scenario: Reranking changes order without changing identity

- **WHEN** the same source fact moves to a different position after reranking
- **THEN** its `evidence_id` SHALL remain unchanged
- **AND** only its display ordinal in that response MAY change

#### Scenario: Evidence identity is cross-platform deterministic

- **WHEN** the same atomic evidence is serialized in another process, input-key order, or supported
  platform
- **THEN** golden vectors SHALL produce the same `ev1_` ID
- **AND** Unicode, WHATWG URL/IDN/query, logical-file, six-digit UTC time, and null/both-locator
  differences defined by v1 SHALL not create a second ID

### Requirement: Structured claims and server-owned rendering

The synthesis boundary SHALL return typed structured sections/items/claims whose material claims
identify claim type, subject, predicate/value, and typed support references. Source facts MUST use
evidence-ID support; count/rank/completeness/set claims MUST use materialized-result-set support; and
empty/error/degradation claims MUST use lane-trace support. The server SHALL validate and render only
after support validation.

#### Scenario: Valid structured answer

- **WHEN** synthesis returns a paper-list item whose title and explanatory claim cite known evidence
  IDs
- **THEN** the server SHALL preserve the structured claims, render them in deterministic order, and
  attach the citations represented by those IDs

#### Scenario: Model text contradicts a typed tuple

- **WHEN** model-suggested text conflicts with a deterministically validated subject/predicate/value
- **THEN** the server SHALL render the claim from the validated tuple rather than preserve the
  contradictory text
- **AND** a section title SHALL NOT carry an unvalidated material assertion

#### Scenario: Unknown evidence reference

- **WHEN** synthesis references an evidence ID not present in the canonical list
- **THEN** validation SHALL fail that claim rather than invent or renumber a source
- **AND** the response SHALL use `partial_result` or `synthesis_error` according to whether a useful
  validated answer remains

#### Scenario: Unsupported material claim

- **WHEN** a material claim has no applicable evidence/result-set/lane support or its support does
  not prove the claim
- **THEN** the claim SHALL NOT appear in a successful answer
- **AND** the unsupported-claim acceptance gate SHALL fail

### Requirement: Runtime material-claim support is fail-closed

The service SHALL validate every externally checkable material claim against its typed support at
runtime. Entity, field, relationship, and membership claims MUST use deterministic typed evidence
checks. Rank, comparative, representative/top, count, completeness, and absence claims MUST bind to
the full materialized result set and its registered predicate/order; successful-empty/error claims
MUST bind to lane trace. Other derived material claims MUST pass an entailment verifier limited to
their cited spans. Formatting/connective text MAY be non-material.

#### Scenario: Structured local fact matches evidence

- **WHEN** a field or relationship claim's typed subject, predicate, and value match the cited
  atomic local evidence
- **THEN** deterministic validation SHALL mark that claim supported without relying on free-form
  text similarity

#### Scenario: Derived material claim is not entailed

- **WHEN** a summary, causal, or non-comparative recommendation-basis claim is not entailed by cited
  evidence spans
- **THEN** that claim SHALL NOT appear in a `success` answer
- **AND** the response SHALL use `partial_result` or `synthesis_error` if required intent can no
  longer be satisfied

#### Scenario: Model claims top rank or complete/empty set

- **WHEN** a claim uses top/most/representative/comparative/count/completeness/absence language
- **THEN** the server SHALL validate it against the full referenced result set and/or lane trace
- **AND** it SHALL reject the claim when only one source span is cited or no set/trace support exists

#### Scenario: Runtime entailment verifier is unavailable

- **WHEN** a required derived material claim cannot be deterministically checked and the entailment
  verifier fails or times out
- **THEN** the service SHALL fail closed with a truthful degraded outcome
- **AND** it SHALL NOT treat offline acceptance judging as runtime support validation

### Requirement: Runtime entailment uses a bounded typed port

The service SHALL call one `ClaimEntailmentVerifier` port for non-deterministic derived claims. Its
production adapter MUST pin an approved existing model/prompt/version before Slice B is Ready, batch
at most 20 claims and 12,000 cited-span characters, use a five-second deadline, expose typed
per-claim verdicts, and receive only cited spans. Tests MUST use a deterministic boundary adapter.

#### Scenario: Verifier input exceeds its bound

- **WHEN** required derived claims or cited spans exceed the frozen batch/character limit
- **THEN** the service SHALL return an explicit partial or synthesis failure
- **AND** it SHALL NOT silently truncate support or split work into unbounded provider calls

### Requirement: Typed outcomes preserve failure meaning

Every canonical chat response MUST contain an outcome status from `success`, `partial_result`,
`no_result`, `retrieval_error`, or `synthesis_error`, plus machine-readable reason codes and any
user-safe degradation notes.

#### Scenario: Successful empty retrieval

- **WHEN** all required retrieval lanes complete successfully and no qualifying evidence exists
- **THEN** the response SHALL use `no_result`
- **AND** it SHALL NOT claim that a provider or retrieval failure proved absence

#### Scenario: Required retrieval lane fails

- **WHEN** a required local retrieval lane errors or times out before its result can be verified
- **THEN** the response SHALL use `retrieval_error` or `partial_result` when another lane produced
  useful validated evidence
- **AND** it SHALL disclose the failed lane in the reason codes or degradation notes

#### Scenario: Evidence exists but synthesis fails

- **WHEN** verified evidence was retrieved but no valid structured synthesis can be produced
- **THEN** the response SHALL use `synthesis_error` unless a deterministic evidence rendering
  satisfies a defined partial-result contract
- **AND** it SHALL NOT use `no_result`

#### Scenario: Query requires clarification or is unsupported

- **WHEN** the system cannot safely select an entity/intent or the requested operation is outside
  supported scope
- **THEN** it SHALL return `partial_result` with `clarification_required` or `unsupported_query`
  reason code, an actionable clarification/refusal payload, and no unsupported factual claim
- **AND** it SHALL NOT represent ambiguity or unsupported scope as a successful empty retrieval
- **AND** a clarification prompt SHALL be a neutral server template; factual option label/hint fields
  SHALL have atomic evidence support, and the candidate/omitted count SHALL have full result-set
  support or the unsupported material SHALL be omitted

### Requirement: Retrieval results expose lane state

The canonical chat-owned retrieval port SHALL return a typed result envelope containing candidates,
per-lane success/empty/error/timeout/skipped status, sanitized error codes, timing, snapshot ID, and
trace ID. It MUST be additive to the shared legacy list-returning retrieval method, whose candidate
selection/ranking remain compatible. The chat service MUST derive outcome from the envelope rather
than infer success from a bare list.

#### Scenario: Empty list follows an embedding failure

- **WHEN** a retrieval lane produces no candidates because embedding, storage, or provider execution
  failed
- **THEN** its lane status SHALL be error or timeout rather than empty
- **AND** chat SHALL produce `retrieval_error` or a truthful `partial_result`, not `no_result`

#### Scenario: All planned lanes succeed empty

- **WHEN** every required lane reports successful empty under the same snapshot
- **THEN** chat MAY produce `no_result`

### Requirement: Canonical list metadata supports stable continuation

The canonical response SHALL include result-set metadata for list answers: result-set ID, domain,
effective predicate, stable ordering, completeness kind, total, page size, opaque next cursor,
snapshot ID, and returned item IDs. The request SHALL accept an optional continuation cursor bound to
that predicate/order/snapshot.

#### Scenario: Type2 list continues on the same snapshot

- **WHEN** a client submits a valid continuation cursor
- **THEN** the next page SHALL use the same predicate, ordering, and snapshot and SHALL neither
  duplicate nor omit an item across page traversal

#### Scenario: Continuation cursor is stale or mismatched

- **WHEN** a cursor belongs to another query/predicate/snapshot or cannot be verified
- **THEN** the response SHALL fail truthfully with a stale/invalid-cursor reason and a restart action
- **AND** it SHALL NOT silently execute a new first page

### Requirement: Continuation materializes an immutable result set

The service SHALL materialize the complete ordered object-ID/sort-tuple values/hashes and manifest
state—without query, snippet, URL, or raw source payload—in an additive reversible store with
predicate/order versions, snapshot fingerprint, owning session, creation time, and 30-minute expiry.
It MUST NOT claim a cross-request PostgreSQL MVCC snapshot. The signed cursor MUST carry result-set
ID, next ordinal, the preceding full-sort-tuple hash (or literal `c1_start`), predicate/order hash,
and expiry.

#### Scenario: Canonical rows change between pages

- **WHEN** source rows are updated after the first page but before a valid continuation request
- **THEN** page enumeration SHALL come from the materialized IDs and remain duplicate/omission-free
- **AND** page evidence SHALL be freshly validated; unavailable/changed source detail SHALL produce
  a disclosed partial result rather than expose stale stored payload

#### Scenario: Result set expires or crosses sessions

- **WHEN** a cursor is expired, its materialized set is gone, or another session presents it
- **THEN** the service SHALL return a stale/invalid-cursor partial result with a restart action
- **AND** TTL cleanup and payload privacy limits SHALL be enforced

### Requirement: Manifest, response, and cursor cryptography is byte-stable and versioned

Result sets MUST use `result-manifest-v1`: RFC 8785 sort-tuple JSON after Unicode NFC/LF
normalization, domain-separated SHA-256 leaf/internal-node hashing over ordinal, canonical object ID,
and sort tuple, deterministic odd-node duplication, and version-prefixed roots/proofs. Response
integrity MUST use `response-integrity-v1`: SHA-256 of the canonical complete public response except
the signature field plus HMAC-SHA256 over version/key/response/session/time/hash binding, with
environment-held rotatable keys. Cursors MUST use `cursor-v1`: canonical version/key/result-set/
ordinal/preceding-sort-tuple-hash/predicate-order/page/session/time payload bytes signed with
HMAC-SHA256. Clarification selection MUST use `clarification-token-v1`, binding response,
query/domain, ordered allowed option IDs, session, issue time, and at-most-30-minute expiry with
HMAC-SHA256. Every `lp` preimage component MUST mean `uint32_be(byte_length) || bytes`; ordinals and
epoch-second timestamps MUST be unsigned 64-bit big-endian. Tokens MUST use
unpadded base64url, constant-time verification, explicit key IDs, and reject noncanonical encoding,
unknown versions/fields/keys, mismatch, tamper, expiry, or cross-session use. V1 algorithms MUST NOT
change in place; a different algorithm requires a new prefix and dual-read migration.

The exact v1 preimages SHALL be: manifest leaf
`SHA-256(0x00 || uint64_be(zero_based_ordinal) || lp_utf8(object_id) || lp(sort_tuple_json))`,
internal node `SHA-256(0x01 || left || right)` with the final odd node duplicated, and empty root
`rm1_ || lowercase_hex(SHA-256(0x02))`; response signature
`HMAC-SHA256(key, lp_utf8("ri1") || lp_utf8(key_id) || lp_utf8(response_id) ||
lp_utf8(session_id) || uint64_be(iat) || uint64_be(exp) || lp(payload_hash_bytes))`; cursor
signature `HMAC-SHA256(key, ASCII("c1") || lp(payload_bytes))`; clarification signature
`HMAC-SHA256(key, ASCII("ca1") || lp(payload_bytes))`. `lp_utf8` applies NFC/LF then UTF-8 and
`lp`; RFC 8785 payloads MUST reject a byte sequence that does not re-encode canonically.

#### Scenario: Workers or clients serialize equivalent inputs differently

- **WHEN** golden inputs include Unicode normalization, JSON numbers, empty/odd result sets, or
  different object-key order across two processes and the backend/frontend language boundary
- **THEN** all conforming implementations SHALL produce the same manifest root, response payload
  hash, and cursor verification result

#### Scenario: Signed token is changed or rotated

- **WHEN** a manifest proof, response field, cursor byte, session binding, timestamp, or key ID is
  changed, or an expired/retired key is used
- **THEN** verification SHALL fail closed before feedback creation or page retrieval
- **AND** active/previous key rotation SHALL pass only within the recorded overlap window

### Requirement: Canonical requests preserve explicit and clarification-bound entity selection

The canonical request MUST retain the existing optional `entity_id_hint` and add optional
`clarification_token`, `continuation_cursor`, and `page_size` fields. A bare entity hint SHALL remain
an explicit user canonical-ID selector and MUST still resolve to source-grounded canonical evidence;
the request value itself MUST NOT satisfy retrieval or citation. A canonical UI selection MUST send
the hint with `clarification-token-v1`; the service MUST reject an ID outside its allowed set,
tampered/stale/cross-session token, query/domain mismatch, or reuse with a different selected ID.
First use MUST atomically record the selection; a concurrent/later retry with the same ID MUST be
idempotently accepted. Legacy mode MUST preserve and golden-test its existing bare-hint round trip.

Replay state MUST live in a reversible 30-minute `chat_clarification_action` TTL store containing
only nonce/response/session/option-set hashes, candidate result-set ID, selected canonical ID,
consumed time, and expiry. It MUST NOT store query, label, hint, snippet, URL, or response body.
Compare-and-set, cleanup, concurrent same/different-ID use, and downgrade after TTL drain MUST be
tested.
`clarification_token` without `entity_id_hint` MUST be invalid; either selection field combined with
`continuation_cursor` MUST be invalid; and a continuation request's page size MUST match the signed
cursor value rather than silently changing page boundaries.

#### Scenario: User selects one supported clarification option

- **WHEN** a canonical client sends one option ID with the signed token from that clarification
- **THEN** the service SHALL resolve that exact canonical object and ground the response from its
  evidence
- **AND** first use SHALL atomically consume the action, an identical retry SHALL select the same ID
  idempotently, and a different-ID replay SHALL fail with `clarification_conflict`

#### Scenario: User sends an explicit bare entity hint

- **WHEN** a caller explicitly sends a valid canonical ID without a clarification token
- **THEN** the service MAY treat it as a direct object selector under the existing compatibility
  behavior
- **AND** it SHALL NOT claim that the hint proves object existence, identity facts, or query match

### Requirement: Canonical public JSON is a versioned discriminated contract

Canonical responses SHALL use `contract_version=canonical-v1`, a stable UUID `response_id`, signed
`response_integrity`, closed object/claim/completeness/support enums, discriminated typed values,
registered predicate/reason codes, sanitized immutable lane assertions, result-set ordered-manifest
hash/proofs, canonical evidence/section/outcome fields, and compatibility metadata. `object_ids` in a
result set MUST be canonical domain object IDs, not answer-item IDs. Required/null/absent behavior
MUST be locked by golden JSON and OpenAPI compatibility fixtures before implementation. Canonical
mode MUST retain every existing public `ChatResponse` field: `query`, `query_type`, `answer_text`,
`citations`, legacy `evidence`, `clarification`, `structured_payload`, `answer_style`,
`citation_map`, and `suggested_followups`. The response signature MUST cover canonical fields and
all retained compatibility/interaction fields.

#### Scenario: Model emits an unregistered predicate or reason

- **WHEN** structured output contains an arbitrary claim predicate, predicate version, value shape,
  object type, or outcome reason not in the canonical schema/registry
- **THEN** Pydantic validation SHALL reject it rather than pass an open dictionary to clients

#### Scenario: Legacy response is returned

- **WHEN** external mode is legacy or shadow
- **THEN** the existing legacy response schema SHALL remain byte/schema-compatible and SHALL omit
  `contract_version` and canonical-only fields

#### Scenario: Canonical response retains interaction fields

- **WHEN** canonical mode returns `clarification_required`
- **THEN** it SHALL include the existing bounded `ClarificationPayload`, additively extended with
  `clarification_token`, per-option typed support refs, and result-set support for `omitted`
- **AND** each visible factual label/hint SHALL validate against atomic evidence; unsupported facts
  SHALL be omitted rather than copied from an ungrounded retrieval dictionary
- **AND** the legacy `default_id` SHALL be display compatibility only and SHALL NOT auto-select an
  ambiguous entity
- **AND** `suggested_followups` SHALL contain at most five server-derived prompts based only on
  validated route/result metadata and SHALL NOT introduce an unsupported factual claim

### Requirement: Canonical feedback is integrity-checked and data-minimized

Canonical feedback SHALL echo the exact canonical response plus its `response_integrity` signature.
The token MUST be HMAC-signed with an environment-managed rotatable key and bind response/session
IDs, canonical hash, issued-at, seven-day expiry, and key ID. The backend MUST reject expired,
tampered, or cross-session input, create feedback idempotently, and persist only minimized metadata:
response ID/version, outcome/reason, claim/object/evidence IDs, source lanes/tiers, result/lane
assertion hashes, and run IDs. It MUST NOT persist or expose through the unauthenticated admin
surface the query, claim/snippet text, URL, raw source/provider payload, cookie, or authorization.
Any durable raw canonical review surface SHALL stop for a separately approved auth/trust-boundary
change.

#### Scenario: User flags a Web or relationship claim

- **WHEN** a canonical response whose legacy projection is lossy receives feedback
- **THEN** signature verification SHALL preserve redacted IDs, lanes/tiers, assertion hashes,
  outcome, and response/run identity without reconstructing from legacy citations
- **AND** admin rendering SHALL expose only the minimized metadata unless an authenticated raw-review
  change is separately approved

#### Scenario: Feedback payload is altered

- **WHEN** the echoed canonical response does not match its integrity signature
- **THEN** feedback SHALL be rejected and no pipeline issue SHALL be created from the tampered data

#### Scenario: Feedback is replayed or expired

- **WHEN** the same valid response/feedback kind is submitted twice
- **THEN** at most one issue SHALL exist for that idempotency key
- **AND** an expired or cross-session token SHALL be rejected without exposing signing details

### Requirement: Compatibility fields are derived from canonical output

During migration, the API SHALL add contract version, canonical evidence, result sets, structured
answer, outcome, and compatibility fields while retaining all current public response fields. In
canonical mode `answer_text`, `citations`, legacy `evidence`, `structured_payload`, `answer_style`,
and `citation_map` MUST be deterministic projections of the validated canonical response, not
independently generated artifacts. `citation_map` MUST map each rendered marker to the exact
canonical `evidence_id`; legacy `evidence` and `structured_payload` MUST NOT become a second
grounding/retrieval source. `answer_style` MUST retain exactly `template | llm_synthesized`, with
deterministic-only output mapped to `template` and accepted structured-model output mapped to
`llm_synthesized`. `clarification` and `suggested_followups` are signed action/interaction fields as
specified above. Legacy and shadow modes MAY run the legacy path as defined by rollout mode.

#### Scenario: Old and new consumers receive one answer

- **WHEN** a valid canonical response is serialized during the compatibility period
- **THEN** new consumers SHALL receive `evidence_items`, structured claims, and `outcome`
- **AND** old consumers SHALL receive all retained legacy fields plus explicit projection status;
  semantic equivalence SHALL be claimed only when `legacy_projection=lossless`

#### Scenario: Legacy dictionaries cannot become a second truth

- **WHEN** canonical mode serializes legacy `evidence` or `structured_payload`
- **THEN** each representable value SHALL be derived from validated canonical evidence, items,
  result sets, or lane assertions
- **AND** unsupported object/source shapes SHALL be declared lossy rather than recast or copied from
  an independent retrieval payload

#### Scenario: Citation arrays cannot diverge

- **WHEN** a compatibility citation is produced
- **THEN** its object, source, snippet, and order SHALL be projected from its canonical evidence
  item
- **AND** no independently assembled citation array SHALL be allowed to replace it

#### Scenario: Legacy citation cannot represent Web or relation evidence

- **WHEN** canonical evidence cannot be represented by the legacy local-entity citation enum
- **THEN** compatibility metadata SHALL mark the projection lossy and list the omitted evidence IDs
- **AND** the projection SHALL NOT cast Web or relationship evidence as a false local entity type
- **AND** canonical cutover SHALL require affected consumers to use canonical evidence

### Requirement: Rollout supports legacy, shadow, and canonical modes

The service MUST support `legacy`, `shadow`, and `canonical` grounded-answer modes. Shadow mode
SHALL externally preserve the legacy response while saving a comparison with canonical execution;
canonical mode SHALL retain derived compatibility fields until consumer cutover is accepted.

#### Scenario: Shadow comparison has no user-visible cutover

- **WHEN** grounded-answer mode is `shadow`
- **THEN** the external response SHALL be byte/schema-compatible with the legacy path and contain no
  `contract_version` or canonical fields
- **AND** canonical evidence, claims, outcomes, validation failures, latency, and semantic diffs
  SHALL be captured for review

#### Scenario: Shadow execution fails or is slow

- **WHEN** bounded off-critical-path shadow enqueue/execution fails or times out
- **THEN** the legacy response status and body SHALL remain unchanged
- **AND** frozen-protocol legacy overhead SHALL remain at most 50 ms p95 and 100 ms p99
- **AND** the shadow failure SHALL be observable internally without persisting sensitive payloads

#### Scenario: Frontend chooses one contract version

- **WHEN** the frontend receives `contract_version=canonical-v1`
- **THEN** it SHALL render only canonical evidence/claims/result sets
- **AND** when `contract_version` is absent it SHALL render only legacy answer/citations, never merge
  both

#### Scenario: Shadow corpus is eligible for cutover

- **WHEN** the frozen suite and privacy-approved redacted shadow corpus contain at least ten cases
  for every supported A-G route plus all outcome/failure and local/Web strata
- **THEN** cutover MAY proceed only with zero schema/citation/unsupported-claim/P0 failures, zero
  frozen semantic regression, identical external legacy behavior in shadow, latency SLO compliance,
  and no persisted secrets/cookies/authorization data

#### Scenario: Immediate rollback

- **WHEN** a canonical rollout violates an acceptance or operational threshold
- **THEN** an operator SHALL be able to restore legacy external behavior by changing the rollout
  mode without reverting data or rewriting response history
- **AND** this external safety switch SHALL NOT be represented as a planner/data/index rollback;
  any real checkpoint rollback SHALL follow the Epic's reverse dependency matrix, mark downstream
  Accepted states Candidate with `invalidated_by`, and block cutover/archive until re-accepted

### Requirement: Local and Web evidence remain distinguishable

Web evidence MUST be typed as Web evidence and include a traceable URL and retrieval/fetch time.
The service SHALL NOT serialize a Web source as a local paper or use it to satisfy a local-object
recall assertion.

#### Scenario: Web supplements an incomplete local answer

- **WHEN** local evidence is insufficient and a Web lane returns a relevant source
- **THEN** the Web evidence SHALL appear in a separately identifiable provenance lane with its URL
  and time
- **AND** the outcome SHALL disclose any remaining local-data limitation

### Requirement: Grounded answer acceptance uses retrieval, citation, and semantics

A P0 chat case SHALL pass only if its expected object or fact is retrieved, correctly cited through
canonical evidence, and expressed correctly and completely for every required intent. Deterministic
validation MUST be combined with an independently configured semantic judge and saved human
adjudication for boundary cases.

#### Scenario: Retrieved but not cited

- **WHEN** the expected paper ID is present in internal retrieval output but absent from the
  answer's canonical evidence references
- **THEN** the case SHALL fail even if the paper title appears as uncited text

#### Scenario: Retrieved and cited but wrong answer

- **WHEN** the expected evidence is retrieved and cited but the answer omits a required intent or
  contradicts the evidence
- **THEN** the semantic stage SHALL fail the case

#### Scenario: Gate command detects a hard failure

- **WHEN** any path-specific P0, unsupported-claim, citation, or regression hard gate fails
- **THEN** the verification command SHALL exit nonzero and retain the raw evidence needed to
  reproduce the failure

### Requirement: Cross-domain evidence has explicit budgets and coverage

The evidence composer SHALL allocate and report evidence by required intent/domain, deduplicate by
stable identity, and detect truncation. It MUST NOT silently discard an applicable joined domain
because another domain was serialized first.

#### Scenario: Evidence budget cannot fit all required domains

- **WHEN** the prompt budget cannot contain the minimum evidence required for every requested
  domain
- **THEN** the service SHALL produce a truthful `partial_result` or a typed synthesis failure with
  truncation details
- **AND** it SHALL NOT return `success` while silently omitting an entire required domain

### Requirement: Frontend citations resolve canonical evidence

The chat UI SHALL render citation markers and source details from canonical evidence order and
identity. It MUST display source type and quality limitations that materially affect trust.

#### Scenario: User opens a citation

- **WHEN** a user activates citation marker N in a canonical answer
- **THEN** the UI SHALL display canonical evidence item N with the same object ID, snippet, source,
  and quality metadata used to validate the claim

#### Scenario: Partial or secondary evidence is shown

- **WHEN** a claim relies on partial data or a secondary relationship
- **THEN** the UI SHALL expose record quality separately from relation tier/limitation rather than
  presenting either as fully verified local evidence
